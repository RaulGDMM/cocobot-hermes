# Overlays geométricos y gestos verificables

Usa esta referencia cuando una composición pinte regiones, bounding boxes, cursores o tarjetas superpuestas sobre capturas reales. La regla principal es: **calcular sobre el raster, no colocar a ojo**.

## 1. Mapear coordenadas con `object-fit: cover`

Para una imagen fuente `sourceW × sourceH` mostrada en un contenedor `boxW × boxH` con `object-fit: cover` y posición centrada:

```js
const scale = Math.max(boxW / sourceW, boxH / sourceH);
const renderedW = sourceW * scale;
const renderedH = sourceH * scale;
const offsetX = (boxW - renderedW) / 2;
const offsetY = (boxH - renderedH) / 2;

const displayBox = {
  left: sourceBox.x * scale + offsetX,
  top: sourceBox.y * scale + offsetY,
  width: sourceBox.width * scale,
  height: sourceBox.height * scale,
};
```

`offsetX` u `offsetY` pueden ser negativos: representan el recorte producido por `cover`. Si cambia `object-position`, ajusta el origen en lugar de asumir centrado.

### Procedimiento

1. Obtén dimensiones reales del raster y bounding boxes de los elementos objetivo.
2. Confirma el tamaño CSS del contenedor y su `object-fit`/`object-position`.
3. Calcula cada caja en coordenadas visibles.
4. Usa esas constantes en CSS; no midas con `getBoundingClientRect()` dentro de callbacks de render.
5. Captura por separado cada fase: píxeles, bloques, desplazamiento y región final.
6. Cuando una fase sustituya a la anterior, desvanece la anterior antes de mostrar la siguiente; acumular todos los overlays dificulta verificar qué señala cada uno.

Para `contain`, usa `Math.min(...)`; los offsets positivos serán letterboxing.

## 2. Animar una selección conforme al cursor

El rectángulo debe nacer en el mismo ancla donde empieza el cursor y crecer hacia el punto final. Para arrastre superior-izquierda → inferior-derecha:

```js
tl.fromTo(region,
  { opacity: 0, scaleX: 0.02, scaleY: 0.08, transformOrigin: '0% 0%' },
  { opacity: 1, scaleX: 1, scaleY: 1, duration: 1.05, ease: 'power2.inOut' },
  dragAt,
);

tl.fromTo(cursor,
  { x: startX, y: startY },
  { x: endX, y: endY, duration: 1.05, ease: 'power2.inOut', immediateRender: false },
  dragAt,
);
```

Invariantes:

- `transformOrigin` coincide con la esquina inicial.
- Cursor y rectángulo usan el mismo inicio, duración y easing.
- El punto final del cursor coincide con la esquina opuesta del rectángulo.
- La caja final corresponde al componente semántico completo, no solo a las letras internas.

Un origen `100% 100%` mientras el cursor avanza desde arriba-izquierda hace que la selección crezca “al revés”.

## 3. Verificar el gesto durante la animación

Un midpoint final no detecta una coreografía invertida. Captura obligatoriamente:

1. justo antes/inicio del arrastre;
2. aproximadamente al 50 %;
3. justo después del final.

Comprueba en la hoja de contacto:

- el cursor parte de la esquina correcta;
- el borde móvil permanece junto al cursor;
- ancho y alto crecen con la dirección del gesto;
- la selección final encaja con el elemento real.

## 4. Orden de capas en contextos 3D

`z-index` puede no resolver el orden visual cuando un ancestro usa `transform-style: preserve-3d`: el navegador también ordena por profundidad transformada.

Preferencia de corrección:

1. Si no se necesita profundidad heredada, elimina `preserve-3d` del grupo y conserva la perspectiva/rotación en cada tarjeta.
2. Usa `z-index` dentro del contexto aplanado.
3. Solo si el 3D heredado es esencial, separa explícitamente con `translateZ(...)` y verifica varios momentos de la rotación.

No des por resuelto un recorte porque el DOM tenga el orden correcto: captura el estado visible antes, durante y después del movimiento 3D.

## 5. Puerta de calidad

Después de corregir:

```bash
npx hyperframes check
npx hyperframes snapshot --at <inicio>,<mitad>,<final> --no-end --output snapshots/review
```

La aceptación requiere ambas cosas: check estructural superado **y** revisión visual de los instantes donde podía aparecer el defecto.