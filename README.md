# md-to-mp3

Egyszerű Python szkript, amely Markdown (`.md`) fájlokból MP3 hangfájlt készít, a Microsoft Edge-TTS neurális, magyar nyelvű hangjaival.

A szkript kitisztítja a Markdown formázást (fejlécek, listák, táblázatok, idézetek, kódblokkok, linkek, félkövér/dőlt kiemelések), majd a megmaradt natúr szöveget felolvastatja és MP3-ba menti.

## Előfeltételek

- Python 3.9+
- [edge-tts](https://pypi.org/project/edge-tts/) csomag

Telepítés:

```bash
pip3 install --user -r requirements.txt
```

vagy közvetlenül:

```bash
pip3 install --user edge-tts
```

## Használat

```bash
python3 md2mp3.py fejezet1.md fejezet2.md
```

Több fájl és minta (glob) is megadható:

```bash
python3 md2mp3.py *.md
```

Ez alapértelmezés szerint az aktuális könyvtár `mp3/` almappájába menti a kimeneteket, fájlonként egy-egy `.mp3`-at (a bemeneti fájl nevével, pl. `fejezet1.mp3`).

### Kapcsolók

| Kapcsoló | Alapérték | Leírás |
|---|---|---|
| `--voice` | `hu-HU-NoemiNeural` | A használt TTS hang (alternatíva pl. `hu-HU-TamasNeural`) |
| `--rate` | `+0%` | Beszédsebesség módosítása, pl. `+10%` vagy `-10%` |
| `--outdir` | `mp3` | Kimeneti mappa |
| `--max-chars` | `4000` | Egy TTS-kérésben elküldött szöveg max. hossza (hosszú fájloknál a szkript automatikusan több részre bontja, majd összefűzi őket) |

### Példa

```bash
python3 md2mp3.py 01_bevezetes.md 02_alapfogalmak.md \
    --voice hu-HU-TamasNeural \
    --rate +10% \
    --outdir hangok
```

## Hogyan működik?

1. Beolvassa a Markdown fájlt, és natúr, felolvasható szöveggé alakítja (a kódblokkokat teljesen kihagyja, a táblázatokat mondatokká alakítja).
2. A szöveget bekezdések mentén darabokra vágja (`--max-chars` méretig), mert az Edge-TTS egy kérésben csak korlátozott hosszúságú szöveget fogad el.
3. Az egyes darabokat az Edge-TTS szolgáltatással MP3-ra szintetizálja.
4. A részeket egyetlen MP3 fájllá fűzi össze, majd törli az ideiglenes fájlokat.
