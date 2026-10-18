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

# Verificacion: ffprobe NO expone el SEI HDR de HEVC como side data y un
# grep binario simple da falsos positivos dentro del dato comprimido —
# hay que recorrer los NALs de mdat (prefijo longitud de 4 bytes) y leer
# los SEI 137 (MDCV) / 144 (CLL) reales. Nota: x265 puede normalizar
# min_lum (p.ej. a 768 = 0.0768 nits); lo que importa verificar son
# primarios, max_lum y MaxCLL.
python3 - "$OUT" "$NITS" <<'PYEOF'
import sys
data = open(sys.argv[1], "rb").read()
nits = int(float(sys.argv[2]))
p = data.find(b"mdat") + 4
END, md, cl = len(data), None, None
while p + 4 <= END:
    n = int.from_bytes(data[p:p+4], "big"); p += 4
    if n <= 0 or p + n > END: break
    nal = data[p:p+n]; p += n
    if (nal[0] >> 1) & 0x3F != 39: continue
    q, pt = 2, 0
    while nal[q] == 0xff: pt += 255; q += 1
    pt += nal[q]; q += 1
    sz = 0
    while nal[q] == 0xff: sz += 255; q += 1
    sz += nal[q]; q += 1
    if pt == 137 and md is None: md = nal[q:q+sz]
    elif pt == 144 and cl is None: cl = nal[q:q+sz]
assert md and cl, "FALTAN los SEI HDR10 (137/144) in-band"
u16 = lambda o: (md[o] << 8) | md[o+1]
got = [u16(i*2) for i in range(8)]
want = [8500, 39850, 6550, 2300, 35400, 14600, 15635, 16450]  # BT.2020+D65 x50000
assert got == want, f"MDCV primarios mal: {got} != {want} (escala x50000)"
maxlum = (u16(16) << 16) | u16(18)
assert abs(maxlum - nits*10000) <= nits*10000*0.01, f"max_lum {maxlum} != {nits} nits"
assert (cl[0] << 8) | cl[1] == nits, f"MaxCLL {(cl[0]<<8)|cl[1]} != {nits}"
print(f"HDR10 SEI OK: BT.2020+D65, mastering {nits} nits, MaxCLL {nits}")
PYEOF
ffprobe -v error -select_streams v:0 -show_entries stream=codec_tag_string,pix_fmt,color_primaries,color_transfer,nb_frames -of csv "$OUT"
echo "YT_HDR10_OK -> $OUT"
echo "Tras subir: la etiqueta HDR aparece cuando YouTube termina la variante VP9/AV1 HDR (20 min-2 h)."
