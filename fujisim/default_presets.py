"""Start-Presets: Rezept-Einstellungen (Zahlen/Optionen) aus fujixweekly.com.

(name, Rezepttext im Kamera-Format, Quelle, Hinweis auf Belichtung/ISO - gehoert nicht ins Preset)
"""
_W = "https://fujixweekly.com/"

DEFAULTS = [
    ("Fujicolor 100 Industrial", """Film Simulation: Reala Ace
Dynamic Range: DR400
Highlight: +0.5
Shadow: +1.5
Color: -1
Noise Reduction: -4
Sharpening: -1
Clarity: -2
Grain Effect: Weak, Small
Color Chrome Effect: Weak
Color Chrome FX Blue: Off
White Balance: 3100K, +8 Red & -8 Blue""",
     _W + "2024/04/05/fujicolor-100-industrial-fujifilm-x100vi-x-trans-v-film-simulation-recipe/",
     "ISO Auto bis 6400, Belichtungskorrektur ca. -1/3 bis +2/3"),
    ("Kodak Gold Max 400 (Expired)", """Film Simulation: Reala Ace
Dynamic Range: DR400
Highlight: -1.5
Shadow: +1.5
Color: -2
Noise Reduction: -4
Sharpening: -2
Clarity: -3
Grain Effect: Strong, Large
Color Chrome Effect: Strong
Color Chrome FX Blue: Strong
White Balance: 6700K, +1 Red & +4 Blue""",
     _W + "2024/12/31/kodak-gold-max-400-expired-fujifilm-x-trans-v-film-simulation-recipe/",
     "ISO Auto bis 6400, Belichtungskorrektur ca. +2/3 bis +1 1/3"),
    ("Pushed Analog", """Film Simulation: Reala Ace
Dynamic Range: DR200
Highlight: +1.5
Shadow: +2
Color: +4
Noise Reduction: -4
Sharpening: -1
Clarity: -3
Grain Effect: Strong, Small
Color Chrome Effect: Strong
Color Chrome FX Blue: Strong
White Balance: Fluorescent 1, -3 Red & -2 Blue""",
     _W + "2024/08/29/pushed-analog-fujifilm-x-t50-x-trans-v-film-simulation-recipe/",
     "ISO Auto bis 6400, Belichtungskorrektur ca. +1/3 bis +2/3"),
    ("Appalachian Negative", """Film Simulation: Nostalgic Neg.
Dynamic Range: DR400
Highlight: -1.5
Shadow: 0
Color: +4
Noise Reduction: -4
Sharpening: +2
Clarity: 0
Grain Effect: Weak, Large
Color Chrome Effect: Strong
Color Chrome FX Blue: Weak
White Balance: 5200K, +2 Red & -2 Blue""",
     _W + "2024/06/18/appalachian-negative-fujifilm-x100vi-x-trans-v-film-simulation-recipe/",
     "ISO Auto bis 6400, Belichtungskorrektur ca. +2/3 bis +1 1/3"),
    ("Kodak Vision3 250D v2", """Film Simulation: Nostalgic Neg.
Dynamic Range: DR200
Highlight: +4
Shadow: +3
Color: -1
Noise Reduction: -4
Sharpening: -2
Clarity: -2
Grain Effect: Strong, Small
Color Chrome Effect: Strong
Color Chrome FX Blue: Off
White Balance: Fluorescent 1, -5 Red & 0 Blue""",
     _W + "2023/12/19/kodak-vision3-250d-v2-fujifilm-x-t5-x-trans-v-film-simulation-recipe/",
     "ISO Auto bis 6400, Belichtungskorrektur ca. 0 bis +2/3"),
    ("1971 Kodak", """Film Simulation: Nostalgic Neg.
Dynamic Range: DR100
Highlight: +2
Shadow: -2
Color: -2
Noise Reduction: -4
Sharpening: -4
Clarity: -4
Grain Effect: Weak, Large
Color Chrome Effect: Strong
Color Chrome FX Blue: Weak
White Balance: 5900K, -1 Red & -6 Blue""",
     _W + "2026/03/25/1971-kodak-a-fujifilm-recipe-for-x-trans-v-cameras/",
     "ISO Auto bis 6400, Belichtungskorrektur ca. -1/3 bis +1/3"),
    ("Nostalgic Americana", """Film Simulation: Nostalgic Neg.
Dynamic Range: DR200
Highlight: -1
Shadow: -1.5
Color: -2
Noise Reduction: -4
Sharpening: -2
Clarity: -3
Grain Effect: Strong, Large
Color Chrome Effect: Strong
Color Chrome FX Blue: Off
White Balance: 5800K, -2 Red & -4 Blue""",
     _W + "2024/04/29/nostalgic-americana-fujifilm-x-t5-x-trans-v-film-simulation-recipe/",
     "ISO Auto bis 6400, Belichtungskorrektur ca. +1/3 bis +2/3"),
    ("California Summer", """Film Simulation: Nostalgic Neg.
Dynamic Range: DR400
Highlight: -2
Shadow: -1
Color: +4
Noise Reduction: -4
Sharpening: -2
Clarity: -4
Grain Effect: Weak, Small
Color Chrome Effect: Strong
Color Chrome FX Blue: Weak
White Balance: 6700K, -1 Red & -6 Blue""",
     _W + "2024/06/04/california-summer-fujifilm-x100vi-x-trans-v-film-simulation-recipe/",
     "ISO Auto bis 6400, Belichtungskorrektur ca. +2/3 bis +1 1/3"),
    ("Reala Ace (X-T5)", """Film Simulation: Classic Negative
Dynamic Range: DR400
Highlight: -1.5
Shadow: -2
Color: +2
Noise Reduction: -4
Sharpening: 0
Clarity: -2
Grain Effect: Weak, Small
Color Chrome Effect: Strong
Color Chrome FX Blue: Strong
White Balance: Auto, -1 Red & +1 Blue""",
     _W + "2023/09/15/reala-ace-fujifilm-x-t5-x-trans-v-film-simulation-recipe/",
     "ISO Auto bis 6400, Belichtungskorrektur ca. -1/3 bis +1"),
    ("Kodak Pro 400", """Film Simulation: Reala Ace
Dynamic Range: DR400
Highlight: -2
Shadow: 0
Color: +1
Noise Reduction: -4
Sharpening: -2
Clarity: -2
Grain Effect: Strong, Small
Color Chrome Effect: Off
Color Chrome FX Blue: Strong
White Balance: 5200K, +2 Red & -3 Blue""",
     _W + "2025/09/06/kodak-pro-400-fujifilm-x-trans-v-film-simulation-recipe/",
     "ISO Auto bis 6400, Belichtungskorrektur ca. +1/3 bis +1"),
    ("Provia Positive", """Film Simulation: Provia/STD
Dynamic Range: DR400
Highlight: -1
Shadow: +1
Color: +4
Noise Reduction: -4
Sharpening: -1
Clarity: +2
Grain Effect: Strong, Small
Color Chrome Effect: Strong
Color Chrome FX Blue: Strong
White Balance: Auto White Priority, +2 Red & -3 Blue""",
     _W + "2026/05/27/fujifilm-recipe-provia-positive/",
     "ISO Auto bis 6400, Belichtungskorrektur ca. +1/3 bis +1"),
    ("CineStill 800T", """Film Simulation: Eterna
Dynamic Range: DR400
Highlight: 0
Shadow: +2
Color: +4
Noise Reduction: -4
Sharpening: -3
Clarity: -5
Grain Effect: Strong, Large
Color Chrome Effect: Strong
Color Chrome FX Blue: Weak
White Balance: Fluorescent 3, -6 Red & -4 Blue""",
     _W + "2024/04/16/cinestill-800t-fujifilm-x-trans-v-film-simulation-recipe/",
     "ISO Auto bis 6400, Belichtungskorrektur ca. -1/3 bis +2/3"),
    ("PRO Negative 160C", """Film Simulation: Reala Ace
Dynamic Range: DR200
Grain Effect: Weak, Small
Color Chrome Effect: Strong
Color Chrome FX Blue: Off
White Balance: Auto, +1 Red & -2 Blue
Highlight: -1
Shadow: -1
Color: +4
Sharpness: -1
High ISO NR: -4
Clarity: -2""",
     _W + "2024/03/27/pro-negative-160c-fujifilm-x100vi-film-simulation-recipe/",
     "ISO Auto bis 6400, Belichtungskorrektur ca. 0 bis +2/3 (X100VI/GFX100 II, X-Trans V)"),
    ("Pacific Blues", """Film Simulation: Classic Neg.
Dynamic Range: DR400
Highlight: -2
Shadow: +3
Color: +4
Noise Reduction: -4
Sharpening: -2
Clarity: -3
Grain Effect: Strong, Large
Color Chrome Effect: Strong
Color Chrome FX Blue: Strong
White Balance: 5800K, +1 Red & -3 Blue""",
     _W + "2022/08/04/fujifilm-x-e4-x-trans-iv-film-simulation-recipe-pacific-blues/",
     "X-E4 (X-Trans IV): ISO Auto bis 6400, Belichtungskorrektur ca. +2/3 bis +1"),
]
