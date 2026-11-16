# AI Játékasszisztens v2.0.0 – fejlesztői útmutató

## Projekt és hatókör
Windows 11, PySide6 GUI, rendszerértesítési tálcaikon. Képernyőrészletet jelöl ki vagy FPS-ben a középső területet rögzíti, majd a JPEG képet OpenAI-kompatibilis multimodális Chat Completions API-ra küldi magyar fordításért. A 2.0 kiadásban hangfordítás (`src/live_translation.py`), offline játékfelismerés (`src/game_detection.py`), többes kijelölést és fájlkezelő műveleteket biztosító előzménykezelés is működik. A fordításokat a felhasználó a jelenlegi Windowsos használatában működőnek jelezte; a teljes kiadási buildet és regressziós ellenőrzést külön kell lefuttatni.

## Olvasási sorrend és fájlok
1. `AI_START_HERE.md` – belépési pont.
2. `docs/AI_FEJLESZTOI_UTMUTATO.md` – jelen részletes útmutató.
3. `README.md` – felhasználói útmutató.
4. `src/assistant.py` – fő alkalmazáskód, ne cseréld le általános sablonnal.
5. `src/live_translation.py` és `src/game_detection.py` – hangfeldolgozás és offline felismerés.
6. `requirements.txt`, `build_portable.bat`, `build_portable.ps1` – build; `src/app.ico` – ikon.

## Kód térképe (src/assistant.py)
- `main()` – QApplication, egy példány (`QLockFile`), tálcaikon, parancsok és szálak életciklusa.
- `Overlay(QWidget)` – modern UI, beállítások, előzmények, mentett ablakgeometria és állapot.
- `RegionSelector(QWidget)` – interaktív területkijelölés és megszakítás.
- `Translator(QThread)` – JPEG base64 kép + fordítási prompt, HTTP-kérés, elsődleges/fallback modell, hibaüzenet.
- `models_endpoint`, `fetch_available_models`, `ModelDiscovery(QThread)` – API-kapcsolat és modelllista.
- `HistoryStore` – előzmények, mappák, másolás/beillesztés, átnevezés, áthelyezés, többes törlés, JSON mentés.
- `src/game_detection.py` – folyamat-, Steam/Epic- és helyi EXE-párosítás alapú, AI-mentes játékazonosítás.
- `src/live_translation.py` – hangfelvétel, átírás, fordítás, megszakítás és helyreállítható feldolgozás.
- `ShortcutRecorder(QLineEdit)` – lenyomott billentyű/egérgomb rögzítése.
- `parse_hotkey`, `normalize_hotkeys`, `Hotkeys` – kombinációk, ütközések, globális Windows bemenet.
- `validate_api_url`, `tls_verify_for` – végpont- és HTTPS-ellenőrzés.
- `load_config`, `write_config`, `save_api_key`, `read_api_key` – beállítások, Credential Manager.
- `migrate_previous_install` – régi adatfájlok átvétele.
- `startup_registered`, `set_startup` – Windows bejelentkezéskori automatikus indítás.

## Funkcionális szerződés – regressziót ne okozz
- Induláskor csak tálcaikon, **nincs konzol vagy automatikus felugró ablak**.
- Jobb kattintásos tálcamenü: területkijelölés, FPS-középső kivágás, előzmények, beállítások, autostart, teljes kilépés.
- Területkijelölés és FPS-fordítás után **csak a fordítás** jelenik meg, előzmények nem.
- A kézi előzmény-nyitott/csukott állapot mentett marad. Az explicit Előzmények parancs (gyorsbillentyű vagy tálcamenü) megnyitja a listát és aktiválást kér; az automatikus fordítás miatti összecsukás nem írja át a kézi állapotot.
- Az előzmények kézi megnyitásakor a program átveszi a fókuszt. A `src/window_focus.py` Windows alatt előtérbe aktiválja az ablakot, majd csak sikeres aktiválás után oldja fel a kurzor korlátozását. Nincs korábbi WM_MOUSEACTIVATE/MA_NOACTIVATE tiltás. Az automatikus fordítás nem hívja ezt a fókuszátadást.
- Az explicit előzménynyitás a Qt minimalizált állapotát is helyreállítja. A show/layout és első újrarajzolás után, a következő Qt-eseményben kér natív aktiválást, majd TOPMOST/NOACTIVATE sorrendfrissítést és újrarajzolást. A kurzor csak sikeres aktiválás után kerül a lista közepére. Sikertelen aktiválást legfeljebb kétszer, 120 ms-onként próbál újra ugyanahhoz a kéréshez kötve; bezárás, előzmény-összecsukás, nézetváltás vagy fókuszvesztés megszakítja. Új kérés érvényteleníti a korábbi időzítőt.
- Egy fordításra kattintás vagy a listán belüli billentyűzetes kiválasztás frissíti a felső fordításmezőt; a lista és az ablakméret megmarad.
- A fordítási, előzményes és beállításnézet külön méretet tárol; az ablak pozíciója is mentett.
- A képernyő- és hangbeállítások közös beállításnézet-méretet használnak. A kettő közötti váltás (navigáció, fogaskerék vagy Vissza) nem módosíthatja az aktuális méretet vagy pozíciót. A régi külön hangbeállítás-méretet betöltéskor figyelmen kívül hagyjuk.
- A beállításlapok közös stílusa és kártya-/mezőelemei a `src/settings_ui.py` modulban találhatók. A lapok tartalma görgethető, a mentés és visszalépés gombjai kívül maradnak a görgethető területen.
- A „kilépés” gyorsbillentyű a látható ablakot rejti el, kijelölés közben megszakít, **nem zárja be** a tálcán futó programot. Teljes kilépés a tálcamenüből.
- Gyorsbillentyűk szabadon rögzíthetők, Mouse3 (görgő), Mouse4, Mouse5 támogatott; játékbeli gombnyomást a hook nem nyeli el.
- Az előzmények műveletei a jobb klikkes menüben vannak; nincs külön műveleti gombsor. Ctrl/Shift többes kijelöléssel mappák és fordítások vegyesen törölhetők, a mappák tartalmával együtt. A megerősítés a deduplikált teljes darabszámot mutatja, és ugyanabban az ablakban marad.
- Fordítások kivágása/másolása/beillesztése: Ctrl+X/C/V; átnevezés: F2; törlés: Delete; új mappa: Ctrl+Shift+N; frissítés: F5; összes kijelölése: Ctrl+A. A kivágás a sikeres beillesztésig nem módosítja a forrást, Esc megszakítja. A listaelemek és a kivágási vágólap stabil `_id` azonosítóval hivatkoznak a fordításokra, nem változó listaindexekkel.
- Az almappák külön azonosítót, nevet és szülőazonosítót kapnak. A régi gyökérmappák neve továbbra is változatlan azonosító; a neveikben lévő elválasztókat nem értelmezzük útvonalként. Az almappák létrehozása v2 mappafájl-formátumot használ (`version`, `folders`: id/name/parent bejegyzések); a régi névlista továbbra is betölthető. Régebbi, csak névlistát ismerő alkalmazásverzióval a v2 mappafájl már nem kompatibilis.
- A mappasorok és a helyválasztó összesített fordításszámot mutatnak, az almappákkal együtt. Az Alt+Fel a szülőre lép; a keresés az aktuális mappafában is keres. A mappatörlés, az átnevezés és a helyreállítási napló a szülő-/névmetaadatokat is kezeli.
- Mappákat is törlő művelet előtt a régi előzmény- és mappaállapot a `forditasok.delete-pending.json` helyreállítási naplóba kerül. Siker után törlődik; félbeszakításkor a következő indulás visszaállítja a korábbi állapotot. Ha a helyreállítás nem sikerül, a további mentés tiltott, a napló megmarad.
- Kép- és hangfordítás esetén a felismert játék mappájába kerülnek a mentések; törölt mappa újralétrejön, amennyiben a játék felismerése sikeres. Ismeretlen játéknál nem szabad az előző játék mappájába menteni.
- A felismerés a Windows-folyamatokból, helyi telepítési adatokból és mentett párosításokból dolgozik. Nincs képalapú vagy hangszöveges AI-játékazonosítás.
- API URL, kulcs, elsődleges/fallback modell és modelllista lekérés a beállításokban.
- Az API **képet** kap, nem pusztán felismert szöveget; nincs folyamatos képernyőmentés.
- A kijelölőablak sikeres kijelölés, túl kicsi terület, Esc és bezárás esetén még az elrejtés előtt törli a régi koordinátákat és képet, majd szinkron újrarajzolással téglalap nélküli képkockát hagy hátra. Az áttetsző háttér CompositionMode_Source módban teljesen felülírja a régi képkockát. Már látható kijelölő ismételt indítása nem készít új képernyőképet a saját rétegéről.
- Sikeres kijelöléskor a tisztítás után, még a kijelölő elrejtése előtt érkezik a `selected` jelzés. A fogadó azonnal megnyitja és aktiválja a „fordítás folyamatban” ablakot. A JPEG-előkészítés és az API-szál indítása a folyamatjelző első festése utáni Qt-eseményre kerül, `preparing` ütközésvédelemmel. Ha a felhasználó a festés előtt elrejti az ablakot, a háttérfeldolgozás akkor is elindul; a bezárással elnyomott eredmény nem nyitja újra az ablakot.
- Ha az operációs rendszer nem küld festési eseményt, egy 1 másodperces figyelő elindítja a várakozó feldolgozást. Normál megjelenésnél nincs ilyen késleltetés; a figyelő a saját munkamenetéhez kötött, és nem indíthat dupla kérést.
- A képi fordítás folyamatjelzője és kész eredménye a panel elrejtéséig előtérben tartott marad. Windows alatt a `keep_on_top` SetWindowPos/NOACTIVATE hívást használ, de nem kér ismételt billentyűzetfókuszt és nem mozgatja a kurzort. Fókuszvesztés után és 250 ms-onként újra érvényesíti a sorrendet. Elrejtéskor az időzítő leáll; az X gombbal, a bezáró gyorsbillentyűvel vagy natív bezárással elrejtett panel késői API-eredménye menthető, de nem nyithatja vissza a panelt. Rejtett vagy minimalizált ablakot az előtérben tartó hívás nem jelenít meg.

## Adatok és biztonság
Felhasználói adatok: `%LOCALAPPDATA%\AIJatekasszisztens`:
- `config.json` – URL, modell, gyorsbillentyűk; API-kulcsot **nem** szabad plaintext tárolni.
- `forditasok.json` – fordítások; `forditas_mappak.json` – mappák.
- A játékfelismerés kézi EXE-párosításai és hangfeldolgozási állapota: a tényleges konfigurációs/mentési implementáció szerint; módosítás előtt ellenőrizd a kódot.
- `ablak_beallitasok.json` – nézet- és ablakállapot.
- `caddy-root.crt` – opcionális Caddy belső CA, csak `.home.arpa` HTTPS-hez.
- `hiba.log` – hibák, titkok nélkül; `application.lock` – egyetlen példány.
API-kulcs: Windows Credential Manager, `keyring`, szolgáltatás `AIJatekasszisztens`, bejegyzés `translation-api-key`.
Távoli API-hoz HTTPS kötelező, HTTP csak localhost. Nyilvános API-hoz normál CA; a belső Caddy CA-t ne alkalmazd globálisan. Az API átirányítás, válaszméret és JPEG méretkorlát védelme maradjon meg. Ne naplózz képernyőképet, API-kulcsot vagy teljes bizalmas API-választ. Régi JSON-mentésekben migrálás után is lehetnek régi kulcsok.

## Folyamatábra szavakban
Terület: `Hotkeys` / tálcamenü → `translate()` → `RegionSelector` → `send_selection()` → JPEG → `Translator` háttérszál → API → `HistoryStore.add()` → `Overlay`.
FPS: `translate_center()` → panel elrejtése → `mss.MSS()` elsődleges monitor → középső százalékos kivágás → `send_selection()`.
Kijelölés megszakításakor nincs API-kérés. Képernyőkép csak kérésre készül. 429 kvótakorlát és 503 átmeneti szolgáltatáshiba lehetséges; automatikus retry-t csak külön felhasználói kérésre adj hozzá.

## Build
Windows, rövid könyvtárútvonal ajánlott (`C:\AIJA`), mert a PySide6 telepítés hosszú útvonalon hibázhat. `build_portable.bat` → PowerShell script → `.buildvenv` → pip → `py_compile` → PyInstaller `--windowed --onedir`. Kimenet: `dist\AIJatekasszisztens\AIJatekasszisztens.exe`; **a teljes mappát** másolni kell. Nincs Inno Setup telepítő. Az aláíratlan EXE-t a Windows Smart App Control blokkolhatja; nem szabad a védelem kikapcsolását vagy megkerülését a build részeként javasolni.

## Tesztelési lista
- Python `py_compile` és független, izolált logikai tesztek.
- Windows alatt tálcás indulás, dupla példány tiltása, autostart, kilépés.
- Területkijelölés és Esc/bezárás, FPS crop, Mouse3/4/5 és egyéni billentyűk.
- Előzmény-állapot kézi megjegyzése, fordítás utáni kompakt mód, ablakméretek és pozíció újraindítás után.
- Mentések/mappák átnevezése és törlése, migráció adatvesztés nélkül.
- API teszt sikeres képes fordítással, hibás kulccsal, 429/503-mal, fallback-kel, modelllistával, Caddy CA-val.
- Ne állíts Windowsos működést igazoltnak pusztán szintaktikai teszt alapján.

## Ismert korlátok
FPS/anti-cheat játékok blokkolhatják a globális hookokat vagy képernyőrögzítést. A fallback modell jelenleg ugyanazt az API URL-t és kulcsot használja. A modelllista nem garantál képfeldolgozási képességet. A „portable” EXE nem jelenti a profil hordozhatóságát: az adatok AppDatában vannak. A képi és hangfordítás közötti játék-mappahozzárendelés, valamint az előzményállapot megőrzése kiemelt regressziós eset.

## Átadási szabály más AI-nak
Mindig a v2.0.0 tényleges `src/assistant.py`, `src/live_translation.py` és `src/game_detection.py` függvényeiből indulj ki, és ellenőrizd a felhasználó ténylegesen futó verzióját. Változtatás előtt készíts másolatot, és ne törölj felhasználói adatot. A működő UI, gyorsbillentyűk és előzményállapot megtartása elsődleges. A kiadáskor az alkalmazáskódban kizárólag a verziókonstans változott; a többi korábbi funkcionális fejlesztés már a jelenlegi forrás része.







