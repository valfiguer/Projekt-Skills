<!-- projekt-tokens:inicio — lo escribe `projekt-tokens instalar`; no lo edites a mano -->
## Presupuesto de contexto

Medido en este proyecto con `projekt-tokens medir`: **el 97,8 % de los tokens es lectura
de caché**, o sea la conversación releída en cada turno. Un resultado de 8.000 caracteres
en el turno 40 de una sesión de 400 no se paga una vez: se paga 360. Ocho reglas, cada
una con la cifra que la justifica.

1. **Todo lo que lee, con tope.** `sed -n '40,90p'` antes que `cat`; `grep -c` o `-l`
   antes que `grep`; `| head -50` al final. — *`grep`+`cat`+`sed` son el 32 % del
   contexto que devuelven las herramientas.*
2. **Un comando compuesto en vez de tres turnos**, y las llamadas independientes en
   paralelo en un solo mensaje. — *el multiplicador es el número de turnos, no el tamaño
   del comando.*
3. **Git: `--stat` antes del diff; `--oneline -n 10` en los logs.** Un `git diff` entero
   de una rama viva no cabe en una cabeza ni en un contexto.
4. **MCP: `fields` con los campos que hacen falta, `limit` pequeño y `cursor` para
   seguir.** — *`list_issues` sin recortar llega a 37.000 caracteres por llamada; con
   `fields`, baja a ~3.000.*
5. **El conector, por dominios**: `?tools=org,search,tasks` en la URL, no `all`. — *el
   catálogo completo son ~130.600 tokens en cada `tools/list`; el perfil por dominios,
   ~30.000.*
6. **Sesión nueva cuando la lectura por turno pase de 200.000.** Se mira con
   `projekt-tokens medir --breve`. — *por encima de ahí cada turno cuesta más que el
   trabajo que hace.*
7. **Los barridos anchos, a un subagente.** Lo que vuelca se queda en SU contexto y al
   hilo principal solo llega la conclusión.
8. **Nunca volcar entero** un `.json`, un `.lock`, un `dist/`, un `node_modules/` ni una
   transcripción `.jsonl`. — *los tres resultados más gordos medidos son exactamente
   eso: 57.663, 47.191 y 47.123 caracteres.*

Lo que **no** es una regla: contestar peor. Si recortar un resultado obliga a pedirlo dos
veces, el recorte ha costado un turno y no ha ahorrado nada.
<!-- projekt-tokens:fin -->
