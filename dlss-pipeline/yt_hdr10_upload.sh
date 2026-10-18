#!/bin/bash
# Entrega HDR10 para YouTube desde el master del pipeline DLSS.
#
# Por qué: YouTube NO clasifica HDR solo con las etiquetas de color
# (smpte2084/bt2020). Necesita el metadata de mastering HDR10
# (SMPTE ST 2086: primarios + punto blanco + nits max/min) y MaxCLL,
# que en HEVC viaja en SEI in-band 137 (MDCV) y 144 (CLL) — igual que
# en las cámaras. Sin eso trata el vídeo como SDR y aplica su tone-map
# genérico (colores "lavados", sin opción HDR en el reproductor).
# YouTube además prefiere HEVC/VP9 para uploads HDR.
#
# Uso:   yt_hdr10_upload.sh <master.mp4> <salida_youtube.mp4> [nits_master=1500]
#
# SINTAXIS x265 (todas las trampas, comprobadas 18/10):
#  - coordenadas y blancos: entero = valor_real x 50000 (¡NO x100000!;
#    pasarlo al doble se acepta en silencio y sale con primarios locos)
#      BT.2020: G(8500,39850) B(6550,2300) R(35400,14600)  D65: WP(15635,16450)
#  - L(max,min) en cd/m2 x 10000: 1500 nits -> 15000000; min 1 -> 0.0001
#  - max-cll usa COMA ("max,min"); con dos puntos se ignora con un warning
set -euo pipefail
IN="${1:?falta master HDR (bt2020/PQ)}"
OUT="${2:?falta archivo de salida}"
NITS="${3:-1500}"
NITS_X10K=$(python3 -c "print(int(float('$NITS')*10000))")

nice -n 10 ffmpeg -y -v warning -stats -i "$IN" \
  -c:v libx265 -preset veryfast \
  -x265-params "crf=18:master-display=G(8500,39850)B(6550,2300)R(35400,14600)WP(15635,16450)L(${NITS_X10K},1):max-cll=${NITS},0" \
  -pix_fmt yuv420p10le \
  -color_primaries bt2020 -color_trc smpte2084 -colorspace bt2020nc -color_range tv \
  -r 60 -tag:v hvc1 -c:a copy -movflags +faststart "$OUT"

# Verificacion: ffprobe NO expone el SEI HDR de HEVC como side data
# (falso negativo) ni trace_headers lo pinta — hay que leer los SEI
# binarios del fichero y comprobar los valores reales.
python3 - "$OUT" "$NITS" <<'PYEOF'
import sys
data = open(sys.argv[1], "rb").read()
nits = float(sys.argv[2])
i, j = data.find(b"\x4e\x01\x89"), data.find(b"\x4e\x01\x90")  # SEI 137 MDCV / 144 CLL
assert i > 0 and j > 0, "FALTAN los SEI HDR10 (137/144) en el fichero"
def payload(p):
    p += 2  # tras cabecera+tipo: size (sin escapes para estas longitudes)
    ln = 0
    while data[p] == 0xff: ln += 255; p += 1
    ln += data[p]; p += 1
    return data[p:p+ln]
b = payload(i)
u16 = lambda o: (b[o] << 8) | b[o+1]
def u32(o): return (u16(o) << 16) | u16(o+2)
got = [u16(0), u16(2), u16(4), u16(6), u16(8), u16(10), u16(12), u16(14)]
want = [8500, 39850, 6550, 2300, 35400, 14600, 15635, 16450]
assert got == want, f"MDCV primarios mal: {got} != {want} (¿escala x50000?)"
assert abs(u32(16) - nits*10000) <= 10000, f"max_lum {u32(16)} != {nits} nits"
c = payload(j)
assert (c[0] << 8) | c[1] == int(nits), f"MaxCLL {(c[0]<<8)|c[1]} != {nits}"
print(f"HDR10 SEI OK: BT.2020+D65, mastering {nits} nits, MaxCLL {int(nits)}")
PYEOF
ffprobe -v error -select_streams v:0 -show_entries stream=codec_tag_string,pix_fmt,color_primaries,color_transfer,nb_frames -of csv "$OUT"
echo "YT_HDR10_OK -> $OUT"
echo "Tras subir: la etiqueta HDR aparece cuando YouTube termina la variante VP9/AV1 HDR (20 min-2 h)."
