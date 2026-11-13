# Akadálymentességi nyilatkozat

## Vállalásunk

Az AI Játékasszisztens célja a játékok nyelvi akadályainak csökkentése. Törekszünk arra is, hogy az alkalmazás kezelése minél több ember számára használható legyen. Az akadálymentességi hibákat és a használatot nehezítő megoldásokra vonatkozó visszajelzéseket fejlesztési feladatként kezeljük.

Ez a dokumentum a jelenlegi lehetőségeket és ismert korlátokat írja le. Teljes körű akadálymentességi audit még nem történt; a projekt nem állít WCAG-megfelelést vagy teljes segédtechnológiai kompatibilitást.

## Célkörnyezet

Az alkalmazás Windows 11-re készül, PySide6/Qt asztali felülettel. A portable kiadás és a forrásból futtatott Windowsos alkalmazás az elsődleges célkörnyezet. A Linux alatt futó logikai és Qt offscreen tesztek nem igazolják a Windowsos segédtechnológiák működését. Más operációs rendszerek asztali használata jelenleg nem támogatott.

## Jelenlegi lehetőségek

- A fordítás, a hangfelvétel és az előzmények megnyitása testreszabható gyorsbillentyűkkel indítható. A részletes kiosztás a [README-ben](README.md#2-fordítás-indítása) található.
- Az FPS-képkivágás a beállított középső képernyőterületet egérrel történő kijelölés nélkül rögzíti; ehhez gyorsbillentyű rendelhető.
- A fordítás és a szövegkönyv kijelölhető, másolható szövegként jelenik meg, és a hosszabb tartalom görgethető.
- Az ablak átméretezhető, a helye és a nézetek mérete megjegyezhető. A képernyő- és hangbeállítások közötti váltás megtartja az aktuális ablakméretet és pozíciót.
- Az előzménylista támogatja a többes kijelölést és a Ctrl+X/C/V, Ctrl+A, F2, Delete, F5 és Ctrl+Shift+N parancsokat. A névmezőben az Enter ment, az Esc megszakítja a szerkesztést.
- A fontosabb hibák és folyamatállapotok szövegesen is megjelennek; a törlés megerősítést kér.

Ezek elérhető funkciók, nem teljes körű akadálymentességi tanúsítások.

## Ismert korlátok és még ellenőrizendő területek

- A keret nélküli ablak, a tálcaikon, az ikongombok és az egyedi megjelenés Windows Narrátorral és NVDA-val nem rendelkeznek dokumentált, teljes körű kézi teszteléssel. A vezérlők felolvasása és a fókuszjelzések további ellenőrzést igényelnek.
- A teljes, kizárólag billentyűzetes munkafolyamat nincs minden nézetben igazolva. A jobb klikkes menü Menü billentyűvel vagy Shift+F10-zel történő elérését is ellenőrizni kell.
- A szabad területkijelölés egérhúzást igényel. Az ablak mozgatása és méretezése is egyedi vezérlőket használ.
- A sötét felület kontrasztját, a Windows kontraszttémáival való együttműködést, a nagyított szöveget és minden DPI-/többmonitoros kombinációt még nem vizsgáltuk teljes körűen.
- Játékok és anti-cheat rendszerek korlátozhatják a globális gyorsbillentyűket vagy a képrögzítést.
- A hangfordítás a felvétel leállítása után készül el; nem valós idejű feliratozás. Az átirat, a beszélőjelölés és a fordítás pontossága a hanganyagtól és a választott szolgáltatóktól függ.

## Akadály bejelentése

Használd az [akadálymentességi bejelentő űrlapot](https://github.com/odordaniel/AI-Jatekasszisztens/issues/new?template=accessibility.yml). Ha az űrlap használata nehézséget okoz, egy [egyszerű issue](https://github.com/odordaniel/AI-Jatekasszisztens/issues/new) is megfelelő.

A bejelentésben lehetőség szerint add meg:

- az alkalmazás verzióját és az érintett képernyőt vagy műveletet;
- a Windows verzióját, a kijelző nagyítását és a használt segédtechnológiát, ha releváns;
- mit próbáltál elérni, hol akadtál el, és milyen működés segítene.

Egészségi állapotodat vagy fogyatékosságodat nem szükséges megadnod. Képernyőkép vagy felvétel nem kötelező; szöveges leírás is elegendő. Ne küldj API-kulcsot, személyes fordítási előzményt vagy más bizalmas adatot.

A visszajelzéseknél a használatot teljesen megakadályozó hibákat különösen fontosnak tekintjük, de konkrét javítási határidőt nem tudunk vállalni. A közreműködéshez a [CONTRIBUTING.md](CONTRIBUTING.md), a közösségi részvételhez a [magatartási kódex](CODE_OF_CONDUCT.md) ad útmutatót.
