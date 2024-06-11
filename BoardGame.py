#This program is not belong to me, only for reference

from abc import ABC, abstractmethod
import os
import numpy as np
import chess.pieces as Pieces
import chess.info_keys as InfoKeys

from buffer.episode import Episode
from learnings.base import Learning
from tqdm import tqdm
from chess import Chess
import torch as T
from utils import save_to_video

from copy import deepcopy
from buffer.episode import Episode
from learnings.base import Learning


import gymnasium as gym
import gym_Chess
import random

class BaseAgent(ABC):
    def __init__(
        self,
        env: Chess,
        learner: Learning,
        episodes: int,
        train_on: int,
        result_folder: str,
    ) -> None:
        super().__init__()
        self.env = env
        self.learner = learner
        self.episodes = episodes
        self.train_on = train_on
        self.current_ep = 0
        self.result_folder = result_folder

        self.moves = np.zeros((2, episodes), dtype=np.uint32)
        self.rewards = np.zeros((2, episodes))
        self.mates_win = np.zeros((2, episodes), dtype=np.uint32)
        self.checks_win = np.zeros((2, episodes), dtype=np.uint32)
        self.mates_lose = np.zeros((2, episodes), dtype=np.uint32)
        self.checks_lose = np.zeros((2, episodes), dtype=np.uint32)

    def update_stats(self, infos: list[dict]):
        for turn, info in enumerate(infos):
            if InfoKeys.CHECK_MATE_WIN in info:
                self.mates_win[turn, self.current_ep] += 1

            if InfoKeys.CHECK_MATE_LOSE in info:
                self.mates_lose[turn, self.current_ep] += 1

            if InfoKeys.CHECK_WIN in info:
                self.checks_win[turn, self.current_ep] += 1

            if InfoKeys.CHECK_LOSE in info:
                self.checks_lose[turn, self.current_ep] += 1

    def take_action(self, turn: int, episode: Episode):
        mask = self.env.get_all_actions(turn)[-1]
        state = self.env.get_state(turn)

        action, prob, value = self.learner.take_action(state, mask)
        rewards, done, infos = self.env.step(action)
        self.moves[turn, self.current_ep] += 1

        self.update_stats(infos)
        goal = InfoKeys.CHECK_MATE_WIN in infos[turn]
        episode.add(state, rewards[turn], action, goal, prob, value, mask)

        return done, [state, rewards, action, goal, prob, value, mask]

    def update_enemy(self, prev: list, episode: Episode, reward: int):
        if prev is None:
            return
        prev[1] = reward
        episode.add(*prev)

    def train_episode(self, render: bool):
        renders = []

        def render_fn():
            if self.env.render_mode != "human":
                renders.append(self.env.render())

        self.env.reset()
        episode_white = Episode()
        episode_black = Episode()
        white_data: list = None
        black_data: list = None
        render_fn()

        while True:
            done, white_data = self.take_action(Pieces.WHITE, episode_white)
            self.update_enemy(black_data, episode_black, white_data[1][Pieces.BLACK])
            render_fn()
            if done:
                break

            done, black_data = self.take_action(Pieces.BLACK, episode_black)
            self.update_enemy(white_data, episode_white, black_data[1][Pieces.WHITE])
            render_fn()
            if done:
                break

        self.add_episodes(episode_white, episode_black)
        self.rewards[Pieces.BLACK, self.current_ep] = episode_black.total_reward()
        self.rewards[Pieces.WHITE, self.current_ep] = episode_white.total_reward()

        if (render or self.env.done) and self.env.render_mode != "human":
            path = os.path.join(self.result_folder, "renders", f"episode_{self.current_ep}.mp4")
            save_to_video(path, np.array(renders))

    def log(self, episode: int):
        print(
            f"+ Episode {episode} Results [B | w]:",
            f"\t- Moves  = {self.moves[:, episode]}",
            f"\t- Reward = {self.rewards[:, episode]}",
            f"\t- Checks = {self.checks_win[:, episode]}",
            f"\t- Mates  = {self.mates_win[:, episode]}",
            "-" * 64,
            sep="\n",
        )

    def tqdm_postfix(self, episode: int):
        return {
            "episode": episode,
            "moves": self.moves[:, episode],
            "rewards": self.rewards[:, episode],
            "checks": self.checks_win[:, episode],
            "mates": self.mates_win[:, episode]
        }

    def train(self, render_each: int, save_on_learn: bool = True):
        for ep in (pbar := tqdm(range(self.episodes))):
            self.train_episode(ep % render_each == 0 or ep == self.episodes - 1)
            self.current_ep += 1
            pbar.set_postfix(self.tqdm_postfix(ep))
            if (ep + 1) % self.train_on == 0:
                self.learn()
                if save_on_learn:
                    self.save()

    def save(self):
        folder = self.result_folder
        np.save(os.path.join(folder, "moves.npy"), self.moves)
        np.save(os.path.join(folder, "rewards.npy"), self.rewards)
        np.save(os.path.join(folder, "mates_win.npy"), self.mates_win)
        np.save(os.path.join(folder, "mates_lose.npy"), self.mates_lose)
        np.save(os.path.join(folder, "checks_win.npy"), self.checks_win)
        np.save(os.path.join(folder, "checks_lose.npy"), self.checks_lose)
        self.save_learners()

    @abstractmethod
    def save_learners(self):
        pass

    @abstractmethod
    def learn(self):
        pass

    @abstractmethod
    def add_episodes(self, white: Episode, black: Episode) -> None:
        pass


class DoubleAgentsChess(BaseAgent):
    def __init__(
        self,
        env: Chess,
        learner: Learning,
        episodes: int,
        train_on: int,
        result_folder: str,
    ) -> None:
        super().__init__(env, learner, episodes, train_on, result_folder)
        self.white_agent = deepcopy(learner)
        self.black_agent = deepcopy(learner)

    def add_episodes(self, white: Episode, black: Episode) -> None:
        self.white_agent.remember(white)
        self.black_agent.remember(black)

    def learn(self):
        self.white_agent.learn()
        self.black_agent.learn()

    def save_learners(self):
        self.white_agent.save(self.result_folder, "white_ppo")
        self.black_agent.save(self.result_folder, "black_ppo")

class Episode:
    def __init__(self) -> None:
        self.goals = []
        self.probs = []
        self.masks = []
        self.values = []
        self.states = []
        self.rewards = []
        self.actions = []

    def add(
        self,
        state: np.ndarray,
        reward: float,
        action,
        goal: bool,
        prob: float = None,
        value: float = None,
        masks: np.ndarray = None,
    ):
        self.goals.append(goal)
        self.states.append(state)
        self.rewards.append(reward)
        self.actions.append(action)

        if prob is not None:
            self.probs.append(prob)
        if value is not None:
            self.values.append(value)
        if masks is not None:
            self.masks.append(masks)

    def calc_advantage(self, gamma: float, gae_lambda: float) -> np.ndarray:
        n = len(self.rewards)
        advantages = np.zeros(n)
        for t in range(n - 1):
            discount = 1
            for k in range(t, n - 1):
                advantages[t] += (
                    discount
                    * (
                        self.rewards[k]
                        + gamma * self.values[k + 1] * (1 - int(self.goals[k]))
                    )
                    - self.values[k]
                )
                discount *= gamma * gae_lambda
        return list(advantages)

    def __len__(self):
        return len(self.goals)

    def total_reward(self) -> float:
        return sum(self.rewards)
    

##JALANKAN
env = gym.make('Chess-v1')
print(env.render())
env.reset()
done = False
while not done:
    action = random.sample(env.legal_moves)
    env.step(action)
    print(env.render(mode='unicode'))
env.close()
