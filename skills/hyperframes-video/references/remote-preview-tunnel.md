# Previsualizar HyperFrames en otro equipo

Usa esta referencia cuando Studio corre en WSL/Linux pero el usuario revisa desde otro Mac o PC de la red.

## Diagnóstico inicial

No adivines la URL. Verifica dónde escucha el servidor:

```bash
ss -ltnp '( sport = :3002 )'
```

Si aparece `127.0.0.1:3002`, ni la IP de WSL ni la IP LAN del host sirven directamente desde otro equipo. No prometas `http://<WSL-IP>:3002`.

## Patrón preferido: túnel SSH inverso al equipo revisor

Cuando WSL ya puede entrar por SSH al Mac/PC del usuario, evita modificar firewall, `netsh portproxy` o configuración de red. Primero comprueba que el puerto remoto está libre:

```bash
ssh -i <key> -o BatchMode=yes <user>@<review-host> \
  'if lsof -nP -iTCP:3002 -sTCP:LISTEN >/dev/null 2>&1; then echo PORT_BUSY; else echo PORT_FREE; fi'
```

Después crea el túnel:

```bash
ssh -i <key> \
  -o BatchMode=yes \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -N -R 127.0.0.1:3002:127.0.0.1:3002 \
  <user>@<review-host>
```

El usuario abre en el equipo remoto:

```text
http://localhost:3002
```

El `127.0.0.1` explícito evita ambigüedad IPv6 y limita el puerto al propio equipo revisor.

## Verificación

Comprueba desde el host remoto, no solo desde WSL:

```bash
ssh -i <key> <user>@<review-host> \
  'curl -sS -I --max-time 5 http://127.0.0.1:3002 | sed -n "1p"'
```

Solo anuncia la URL después de recibir `HTTP/1.1 200 OK` o equivalente.

## Ciclo de vida

Studio y el túnel son procesos de larga duración:

- arráncalos como procesos background rastreables;
- usa keepalive en SSH;
- tras compactación, reinicio o pérdida de sesión, comprueba ambos procesos antes de decir que la URL sigue disponible;
- si alguno murió, relanza Studio primero y el túnel después;
- recuerda que el túnel es temporal y termina con su proceso SSH.

Este patrón es para preview temporal. Una URL estable o compartida fuera de la sesión requiere publicar el proyecto o configurar red de forma explícita con aprobación del usuario.