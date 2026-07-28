# Third-Party Licenses

The addon code itself is licensed under GPL-3.0-or-later (see `LICENSE`).
The bundled binary assets below carry their own licenses, listed here as
required by those licenses.

## Fonts (`assets/fonts/`)

| Family | Files | Author | License | License text |
|---|---|---|---|---|
| Inter | `Inter.ttf` | The Inter Project Authors | SIL Open Font License 1.1 | `assets/fonts/Inter-OFL.txt` |
| IBM Plex Sans | `IBMPlexSans.ttf` | IBM Corp. | SIL Open Font License 1.1 | `assets/fonts/IBMPlexSans-OFL.txt` |
| Selawik | `selawk.ttf`, `selawkb.ttf`, `selawkl.ttf`, `selawksb.ttf` | Microsoft Corporation | SIL Open Font License 1.1 | `assets/fonts/Selawik-OFL.txt` |

Used as the Steam / PlayStation / Xbox toast fonts respectively, replacing
the platforms' proprietary fonts (Motiva Sans, SST, Segoe UI) which cannot
be redistributed.

Note: Selawik is distributed by Microsoft under the SIL OFL, not MIT —
double-checked against the license file in its own repository
(`microsoft/Selawik`), which states OFL 1.1 despite some third-party
listings describing it as MIT.

## Sounds (`assets/standart.wav`, `assets/rare.wav`)

"Game Pickup" by IENBA — <https://freesound.org/s/698768/>
License: CC0 1.0 Universal (public domain dedication), full text in
`assets/CC0-1.0.txt`. No attribution required; credited here anyway.

## Everything else

All icons (`icons/*.png`), `assets/blender_icon.png`, `assets/glow_mask.png`,
`assets/spritesheet.png`, `assets/trophy_full.png`,
`assets/trophy_no_handles.png` are original artwork created for this
project and are covered by the same GPL-3.0-or-later license as the code
(see `LICENSE`).
