#Hi! Im Muhammad Wisnu Maulana! Glad you are here!


import os
import re
import warnings
import time
import io

#Ini diperlukan untuk memakai cairosvg (hanya untuk pengguna jendela)
os.environ["path"] += r";C:\Program Files\UniConvertor-2.0rc5\dlls"

import customtkinter as ctk
import threading
import numpy as np
from PIL import Image
from outlines import models
from outlines import generate
import chess
import chess.svg
import cairosvg
import numpy as np

# warnings.filterwarnings("ignore")

def legal_moves_reg(board):
    legal_moves = list(board.legal_moves)
    legal_moves = [board.san(i) for i in legal_moves]
    legal_moves = [re.sub(r"[+#]", "", i) for i in legal_moves]
    legal_moves = "|".join(re.escape(i) for i in legal_moves)

    return legal_moves

def board_to_CTKImage(board, first:bool=True):
    if first:
        svg = chess.svg.board(board)
    else:
        moves = board.peek()
        svg = chess.svg.board(board, arrows=[(moves.from_square, moves.to_square)])
    
    img = cairosvg.svg2png(svg.encode("utf-8"))
    img = Image.open(io.BytesIO(img))
    return ctk.CTkImage(img, size=(400,400))

class ChessAgent():
    def __init__(self, model_id:str, t_budget:int = 180, device:str="cuda", tqdm_format:str="{desc} {n:.0f} seconds left | Elapsed: {elapsed}", model_prompt:str="") -> None:
        self.model = models.transformers(model_id, device=device) if not model_id.lower() == "random" else "random"
        self.move = []
        self.t_budget = t_budget
        self.tqdm_format = tqdm_format
        self.model_prompt = model_prompt

    def generate_move(self, pattern, prompt):
        if self.model == "random":
            return np.random.choice(pattern.split("|"))
        
        return generate.regex(self.model, pattern)(self.model_prompt + "\n" + prompt)
        
class Frame(ctk.CTkFrame):
    def __init__(self, mainWd, text="Gambar", side ="left") -> None:
        ctk.CTkFrame.__init__(self, mainWd)
        self.mainWd = mainWd
        self.setup(text=text, side=side)
    
    def setup(self, text, side):
        self.out = ctk.CTkLabel(self, text=text, font= ("sans-serif", 30))
        self.out.pack(fill= "both", expand=True, padx=5, pady=5)
        self.out.configure(anchor="center")
        self.img_label = ctk.CTkLabel(self, text="")
        self.img_label.pack(side=side, fill= "both", expand="yes", padx=10, pady=10)
    
    def img_update(self, img):
        self.img_label.configure(image=img)
        self.img = img

class TextFrame(ctk.CTkFrame):
    def __init__(self, main, text="Video", side="left"):
        ctk.CTkFrame.__init__(self, main)
        self.text = ""
        self.setup(text=text, side=side)

    def setup(self, text, side):
        self.out = ctk.CTkLabel(self, text=text, font= ("sans-serif", 30))
        self.out.pack(fill= "both", expand=True, padx=5, pady=5)
        self.out.configure(anchor="center")
        self.text_label = ctk.CTkTextbox(self, state = "disabled", width=500, height=500)
        self.text_label.pack(side=side, fill= "both", expand="yes", padx=10, pady=10)
    
    def text_update(self, txt):
        self.text += txt or ""
        self.text_label.configure(state="normal")
        self.text_label.delete(0.0, ctk.END)
        self.text_label.insert(ctk.END, self.text)


class MainWd():
    def __init__(self) -> None:
        self.mainWd = ctk.CTk()
        self.run = True
        self.window_size_init= [980,720]
        self.iter = 1
        self.first_move = True

        self.board = chess.Board()
        self.prompt = f"{self.iter}."
        self.currentPlayer = None
        self.models_id = ["mlabonne/chesspythia-70m", "AGundawar/chess-410m"]

        self.models = [ChessAgent(self.models_id[0]), ChessAgent(self.models_id[1])]

        self.place_component()

        self.comment.text_update(f"PUTIH : {self.models_id[0]}\nHITAM : {self.models_id[1]}\n\n\n")
        self.board_frame.img_update(board_to_CTKImage(self.board, True))

        self.mainWd.geometry(f"{self.window_size_init[0]}x{self.window_size_init[1]}+10+10")
        self.mainWd.minsize(980,560)
        self.mainWd.title("MultiAgent Chess")
        self.mainWd.after(100, self.loop)

    def place_component(self):
        self.board_frame = Frame(self.mainWd, text="BOARD")
        self.board_frame.place(relx=0, rely=0.55, x=10, anchor="w")

        self.comment = TextFrame(self.mainWd, "PERGERAKAN")
        self.comment.place(relx=1, rely=0.5, x=-10, anchor="e")

    def close(self):
        self.run = False
        self.mainWd.destroy()

    def cek_skak(self):
        if self.board.is_checkmate():
            return "\nSKAK"
        if self.board.is_stalemate():
            return "\nREMIS"
        if self.board.is_insufficient_material() or self.board.can_claim_threefold_repetition() or self.board.can_claim_fifty_moves():
            return "\nSERI"
        
        return "Tidak diketahui"
    
    def loop(self):
        self.currentPlayer = self.models[0] if self.board.turn else self.models[1]

        pattern = legal_moves_reg(self.board)
        curr_move = self.currentPlayer.generate_move(pattern, self.prompt + f" {self.iter}." if not self.models[1] else "")

        try:
            mvs = curr_move.strip()
            mvs = self.board.parse_san(mvs)
            
            if mvs not in self.board.legal_moves:
                print(f"Illegal move: {mvs}")

            if self.first_move:
                mov_txt = f"1.{curr_move} "
                self.first_move = False
            else:
                if self.board.turn:
                    mov_txt = f"{self.iter+1}.{curr_move} "
                    self.iter += 1
                else:
                    mov_txt = f"{curr_move} "

            self.prompt += mov_txt
            self.board.push(mvs)
            self.comment.text_update(mov_txt)
            self.board_frame.img_update(board_to_CTKImage(self.board, False))
        except ValueError:
            print(f"Kesalahan saat bergerak : {curr_move}")

        if self.board.is_game_over():
            self.comment.text_update(f"\n{self.cek_skak()}")
            self.run=False

        if self.run == True:
            self.mainWd.after(15, self.loop)

    def start(self):
        self.mainWd.mainloop()


if __name__ == "__main__":
    window = MainWd()
    window.start()
