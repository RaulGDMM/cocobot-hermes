#!/bin/bash
# Entrega HDR10 para YouTube desde el master del pipeline DLSS.
#
# Por qué: YouTube NO clasifica HDR solo con las etiquetas de color
# (smpte2084/bt2020). Necesita el metadata de mastering HDR10
# (SMPTE ST 2086: primarios + punto blanco + nits max/min) y MaxCLL.
# Sin eso lo trata como SDR y aplica su tone-map genérico (colores
# "lavados" y sin opción HDR en el reproductor). Ademas prefiere
# HEVC/VP9 para uploads HDR — de ahi re-codificar a HEVC main10 hvc1.
#
# Uso:   yt_hdr10_upload.sh <master.mp4> <salida_youtube.mp4> [nits_master=1500]
# Ojo sintaxis x265: max-cll usa coma ("max,min"); con dos puntos se
# ignora en silencio con solo un warning. El master-display va en
# unidades enteras: coordenadas x100000, luminancias x10000 cd/m2.
set -euo pipefail
IN="${1:?falta master HDR (bt2020/PQ)}"
OUT="${2:?falta archivo de salida}"
NITS="${3:-1500}"
NITS_X10K=$(python3 -c "print(int(float('$NITS')*10000))")
MAXCLL="${NITS},0"

nice -n 10 ffmpeg -y -v warning -stats -i "$IN" \
  -c:v libx265 -preset veryfast \
  -x265-params "crf=18:master-display=G(17000,79700)B(13100,4600)R(70800,29200)WP(31270,32900)L(${NITS_X10K},1):max-cll=${MAXCLL}" \
  -pix_fmt yuv420p10le \
  -color_primaries bt2020 -color_trc smpte2084 -colorspace bt2020nc -color_range tv \
  -r 60 -tag:v hvc1 -c:a copy -movflags +faststart "$OUT"

# verificacion: el side data del primer frame debe traer ambos bloques
SD=$(ffprobe -v error -select_streams v:0 -read_intervals "%+#1" \
      -show_entries frame=side_data_list -of json "$OUT")
echo "$SD" | grep -q "Mastering display metadata" || { echo "FALTA MDCV (ST2086)"; exit 1; }
echo "$SD" | grep -qi "Content light" || { echo "FALTA MaxCLL"; exit 1; }
ffprobe -v error -select_streams v:0 -show_entries stream=codec_name,pix_fmt,color_primaries,color_transfer -of csv "$OUT"
echo "YT_HDR10_OK -> $OUT"
echo "Tras subir: YouTube tarda (20 min-2 h) en generar la variante HDR;"
echo "la etiqueta HDR aparece en Calidad cuando termine."
