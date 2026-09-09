# Omarchy Cockpit

Gem en vinduesopsætning, se den i Omarchy-baren, og gendan den senere.
Panelet og backendens beskeder bruger engelsk som standardsprog.
Bygget til den installerede Hyprland 0.56.2 med Lua-konfiguration og Dwindle.
Ingen pip-pakker, ekstra shell-proces eller privilegeret installation.

**Eksperimentel alpha — `0.1.0-alpha.2`.** Samme skærmopsætning kræves ved
gendannelse, og en fuld systemgenstart er endnu ikke testet.

## Brug

Installér via Omarchys plugin-system, og klik derefter **▦ Cockpit** i baren:

```bash
omarchy plugin add https://github.com/Danubii/omarchy-cockpit --enable
```

Navngiv opsætningen og vælg **Save**.
Vælg et snapshot for at se et preview af hvert workspace. **Check** undersøger,
om det kan gendannes uden at ændre vinduer. **Restore** starter manglende apps og
genopbygger opdelingen. Status viser den målte afvigelse bagefter (højst 2 px tæller
som succes; JSON-rapporten indeholder det faktiske tal).

Tastatur: **S** rediger navn, **Enter** gem under redigering, **↑↓** vælg snapshot,
**C** kontrollér, **R** eller **Enter** gendan det valgte snapshot, **A** slå auto til/fra,
**Esc** luk (under navneredigering afslutter første Esc redigeringen).
Kontrollerne har beskrivende navne til tilgængelighedsværktøjer. Det valgte snapshot
og auto-status er fremhævet visuelt; lange lister og previews kan rulles med mus eller
touchpad. Hold markøren over en knap for en kort forklaring.

**Auto** gemmer hvert minut i ti roterende snapshots. Funktionen er kun aktiv,
mens widgetten er indlæst, og indstillingen nulstilles ved shell-genstart.
Navngivne snapshots bliver liggende efter genstart. Gendannelse efter login er
manuel i denne prototype; der er ingen autostart af apps.

Kommandolinjen kan bruges direkte fra standardinstallationen:

```bash
python3 ~/.config/omarchy/plugins/zeq0r.cockpit/cockpit.py save "Mit cockpit"
python3 ~/.config/omarchy/plugins/zeq0r.cockpit/cockpit.py restore "Mit cockpit" --dry-run
python3 ~/.config/omarchy/plugins/zeq0r.cockpit/cockpit.py restore "Mit cockpit"
python3 ~/.config/omarchy/plugins/zeq0r.cockpit/cockpit.py list
```

Snapshots: `~/.local/share/omarchy-cockpit/` (private JSON-filer).
Rapport: `last-restore-report.json`. Før en ændring gemmes `before-restore`, som
kan gendannes på samme måde, når eventuelle nyåbnede vinduer er flyttet væk.
Fejl efter start kan efterlade en delvist gendannet opsætning; ingen automatisk rollback.
Gendannelse lukker aldrig eksisterende vinduer.

## Understøttelse og grænser

- Dwindle: rekonstruerer et binært split-træ fra geometri og retter størrelserne.
- Floating-vinduer: gemmer og gendanner placering og størrelse.
- Workspaces og skærmtilknytning gemmes. Samme skærmnavne, opløsning, skalering,
  rotation og reserveret panelplads kræves; skærmens globale position må ændre sig.
- Foot: genåbner en terminal i shellens arbejdsmappe med et unikt app-id.
  Kørende kommandoer, scrollback og shell-tilstand genskabes ikke.
- Chrome/Chromium: starter et nyt vindue. Faner og browserprofiler gemmes ikke.
- Andre apps kan genbruges, hvis åbne, eller gives en eksplicit startkommando.
- Grupper, fullscreen og pinned afvises inden ændring; almindelige og special-workspaces gemmes.
- Ekstra vinduer på mål-workspace afvises. Flere vinduer fra samme app matches efter
  titel, workspace og geometri.
- Vinduesregler, minimumsstørrelser eller fokusændringer under arbejdet kan forhindre
  nøjagtig gendannelse. Brug målerapporten; en API-kvittering er ikke en geometrisk test.
- Flere skærme er implementeret med forudgående kontrol, men kun én skærm er live-testet.
- En rigtig systemgenstart er endnu ikke testet. Live-testen lukker testvinduerne og
  gendanner dem som nye processer fra disk med ændret sessionsidentitet.

Tilpas en startkommando (argumenter sendes direkte, uden shell):

```bash
omarchy-cockpit show "Mit cockpit"  # find vinduets slot
omarchy-cockpit recipe "Mit cockpit" SLOT -- program argument
```

Programmet skal åbne et vindue med snapshot'ets `restore_class`. Kommandoen kan
tilpasses i JSON, hvis appen kræver en bestemt klasse eller profil. Automatisk
start er bevidst begrænset til kendte opskrifter; `/proc`-kommandoer genafspilles ikke.

## Udvikling og validering

Kildekode ligger i denne mappe; `bash install.sh` kopierer pluginfilerne til
`~/.config/omarchy/plugins/zeq0r.cockpit/`, validerer og aktiverer dem via Omarchy.
Shell-konfigurationen sikkerhedskopieres ved installation. Der ændres ingen Hyprland-
konfigurationsfiler. Deaktivér med `omarchy plugin disable zeq0r.cockpit`.
Installationen genstarter Omarchy-shellen for at tømme QML-cachen. Den installerede
Quickshell-version beholdt ellers en gammel panelkomponent efter hot reload.

```bash
python3 -m unittest -v test_cockpit.py
python3 live_test.py  # åbner og lukker kun sine egne testterminaler
omarchy plugin validate .
```

Testet 5. september 2026: 10 unit-tests bestået. Fire live-scenarier bestået med
0 px afvigelse: tre eksisterende vinduer efter flytning, nye processer fra snapshot,
fire tiled vinduer med forskellige splits, samt blandet floating/tiled.
Live-testen skriver resultater til `live-test-results.json` (ikke med i repositoryet). Brugerens tre oprindelige vinduers geometri blev
kontrolleret efter testene og var uændret.
Panelets åbning, lukning, tastaturbaserede gem og kontrol er også testet i den
kørende shell. Pluginet overlevede en shell-genstart. En eksisterende portal-advarsel
i shell-loggen er uafhængig af pluginet; der kom ingen Cockpit-runtimefejl.

QML følger [Omarchys udviklingsguide](https://plugins.omarchy.org/develop.html)
og de installerede `qs.Ui`-komponenter. `qmllint` findes på denne maskine som
`/usr/lib/qt6/bin/qmllint`. Quickshells `qs`-import kræver en importrod med `qs`
peget på `/usr/share/omarchy/shell`; almindelig lint har advarsler om dynamiske
shell-typer og Quickshells QProcess-metadata. Kontroller også det indlæste plugin
og shellens runtime-log.

Undersøgt som teknisk reference: [hypr-persist](https://github.com/ngamber/hypr-persist).
Denne prototype bruger sin egen Python-motor og kræver ikke Rust eller hypr-persist.
Lua-dispatcher-reference: [Hyprland](https://wiki.hypr.land/Configuring/Basics/Dispatchers/).

Næste forsøg: tmux-sessioner til terminalindhold, browser-specifik sessionsintegration,
valg af korrekt vindue ved tvetydighed og en tilpasningsstrategi for frakoblede skærme.
