# AI Játékasszisztens

**Játssz a saját nyelveden.**

Nyílt forráskódú, magyar nyelvű AI-fordító Windowsra, amely segít megérteni a játékokban megjelenő idegen nyelvű szövegeket.

Kijelölöd a képernyő megfelelő részét, az alkalmazás pedig mesterséges intelligencia segítségével magyarra fordítja a tartalmát — anélkül, hogy ki kellene lépned a játékból.

[![Windows](https://img.shields.io/badge/Windows-11-0078D4?style=flat-square&logo=windows11&logoColor=white)](https://www.microsoft.com/windows/windows-11)
[![License](https://img.shields.io/github/license/odordaniel/AI-Jatekasszisztens?style=flat-square)](LICENSE)
[![Build](https://img.shields.io/github/actions/workflow/status/odordaniel/AI-Jatekasszisztens/build.yml?branch=main&style=flat-square&label=Windows%20build)](https://github.com/odordaniel/AI-Jatekasszisztens/actions)
[![Release](https://img.shields.io/github/v/release/odordaniel/AI-Jatekasszisztens?style=flat-square&label=Release)](https://github.com/odordaniel/AI-Jatekasszisztens/releases/latest)

**[Legfrissebb verzió letöltése](https://github.com/odordaniel/AI-Jatekasszisztens/releases/latest)** · [Forráskód](https://github.com/odordaniel/AI-Jatekasszisztens) · [Hibabejelentés](https://github.com/odordaniel/AI-Jatekasszisztens/issues)

---

## Áttekintés

Az AI Játékasszisztens azoknak készült, akik szeretnék megérteni a játékok történetét, párbeszédeit, feladatait és egyéb szövegeit, akkor is, ha a játék nem kínál magyar nyelvet.

Az alkalmazás egy kijelölt képernyőrész képét küldi el egy képfeldolgozásra alkalmas AI-modellnek, amely felismeri és magyarra fordítja a megjelenő szöveget.

Nincs szükség a játék fájljainak módosítására vagy külön magyarítás telepítésére.

## Funkciók

| Funkció | Leírás |
|---|---|
| **AI-alapú fordítás** | Játékbeli szövegek értelmezése és magyarra fordítása |
| **Területkijelölés** | A fordítandó képernyőrész szabadon kiválasztható |
| **FPS-gyorsfordítás** | A képernyő középső területének gyors feldolgozása |
| **Gyorsbillentyűk** | Testreszabható billentyű- és támogatott egérgomb-kombinációk |
| **Fordítási panel** | A magyar szöveg külön, könnyen kezelhető ablakban jelenik meg |
| **Fordítási előzmények** | Korábbi fordítások megőrzése, keresése és rendszerezése |
| **AI-modellválasztás** | Elsődleges és tartalék modell beállítása |
| **Saját API-végpont** | Kompatibilis helyi vagy távoli AI-szolgáltatás használata |
| **Windows-integráció** | Tálcaikon és opcionális automatikus indítás |
| **Hordozható kiadás** | Használat hagyományos telepítő nélkül |

## Letöltés és telepítés

**Rendszerkövetelmény:** Windows 11.

1. Nyisd meg a [Releases](https://github.com/odordaniel/AI-Jatekasszisztens/releases/latest) oldalt.
2. Töltsd le a legfrissebb `Windows-portable.zip` csomagot.
3. Csomagold ki a teljes ZIP-et egy állandó mappába.
4. Indítsd el az `AIJatekasszisztens.exe` fájlt.
5. A program a Windows értesítési területén is elérhető lesz.

A hordozható csomag minden szükséges alkalmazásfájlt tartalmaz. A futtatásához nem kell külön Pythont telepíteni.

> **Windows biztonság:** a kiadott EXE jelenleg nincs digitálisan aláírva. A Windows SmartScreen vagy Smart App Control ezért figyelmeztethet, illetve blokkolhatja az indítást. A program nem próbálja megkerülni ezeket a védelmeket.

## Első használat

### 1. AI-szolgáltatás beállítása

Nyisd meg az alkalmazás beállításait, majd add meg:

- Az AI-szolgáltatás API-végpontját.
- Az API-kulcsot, ha a szolgáltatás megköveteli.
- Egy képek értelmezésére képes elsődleges AI-modellt.
- Opcionálisan egy tartalék modellt.

Az alkalmazás támogatja a kompatibilis chat completions API-végpontokat, és képes lekérni a szolgáltató elérhető modelljeit.

Az AI-szolgáltatás biztosítása és esetleges használati költsége a választott szolgáltatótól függ.

### 2. Fordítás indítása

Indíts el egy játékot, majd használd a gyorsbillentyűket:

| Gyorsbillentyű | Művelet |
|---|---|
| `Ctrl + Shift + T` | Képernyőterület kijelölése és fordítása |
| `Ctrl + Shift + H` | Fordítási előzmények |
| `Ctrl + Shift + Q` | Ablak bezárása vagy kijelölés megszakítása |

Az FPS-gyorsfordításhoz külön gyorsbillentyű rendelhető.

A gyorsbillentyűk a beállításokban módosíthatók.

### 3. Fordítások kezelése

A korábban elkészült fordítások az előzmények között visszakereshetők. A bejegyzéseket átnevezheted, mappákba rendezheted vagy törölheted.

## Adatvédelem és biztonság

A projekt célja, hogy az AI-fordítás használata mellett a felhasználó megtarthassa az ellenőrzést a saját adatai és AI-szolgáltatása felett.

- **Kérésre történő képfeldolgozás:** képernyőkép csak kifejezett fordításkéréskor kerül az AI-végpontra.
- **Biztonságos API-kulcs tárolás:** a kulcsot a Windows Credential Manager kezeli.
- **Titkosított kapcsolatok:** távoli végpontokhoz HTTPS szükséges; a titkosítatlan HTTP kizárólag localhost esetén engedélyezett.
- **Helyi beállítások:** a beállítások és fordítási előzmények a felhasználói profilban tárolódnak.
- **Ellenőrizhető kiadások:** a verziózott ZIP-csomagokhoz SHA-256 ellenőrzőösszeg tartozik.
- **Nyílt forráskód:** az alkalmazás működése és biztonsági megoldásai szabadon ellenőrizhetők.

A fordításhoz elküldött képek feldolgozását és esetleges tárolását a kiválasztott AI-szolgáltató adatkezelési szabályai is befolyásolják.

További információ: [Security Policy](SECURITY.md).

## Frissítés

1. Zárd be az alkalmazást a tálcaikon **Kilépés** menüpontjával.
2. Töltsd le a legújabb verziót.
3. Cseréld le a korábbi programkönyvtárat az új csomag tartalmára.
4. Indítsd újra az alkalmazást.

A felhasználói beállítások és előzmények külön, a `%LOCALAPPDATA%\AIJatekasszisztens` könyvtárban találhatók, így a program mappájának cseréje önmagában nem törli őket.

## Fejlesztés

Az alkalmazás Pythonban készül, PySide6-alapú grafikus felülettel. A Windows-portable kiadást PyInstaller állítja elő.

**Főbb technológiák:** Python · PySide6 · MSS · Pillow · Requests · Windows Credential Manager · PyInstaller

A projekt GitHub Actions munkafolyamatai:

- Windows-build minden releváns kódváltoztatásnál.
- Függőségek telepítése SHA-256 hash-ellenőrzéssel.
- Automatikus ZIP-csomagkészítés és ellenőrzőösszeg-generálás verziózott kiadásokhoz.
- Dependabot által előkészített függőségfrissítések.

### Helyi build

A forráskód letöltése vagy klónozása után Windows alatt futtasd:

```powershell
.\build_portable.bat
```

A sikeres build eredménye a `dist\AIJatekasszisztens` mappában található.

A projekt függőségeit a `requirements.txt` és `requirements-lock.txt` fájlok tartalmazzák.

## Közreműködés

A hibajelentések, fejlesztési ötletek és javítási javaslatok szívesen fogadottak.

- [Hibajelentés és funkciójavaslat](https://github.com/odordaniel/AI-Jatekasszisztens/issues)
- [Pull Requestek](https://github.com/odordaniel/AI-Jatekasszisztens/pulls)
- [Közreműködési útmutató](CONTRIBUTING.md)

## Licenc

A projekt az [MIT-licenc](LICENSE) feltételei szerint használható, módosítható és terjeszthető.

---

**AI Játékasszisztens**

*Kevesebb nyelvi akadály. Több játékélmény.*

 Fejlesztő: ChatGPT
Ötletgazda: [Ódor Dániel](https://github.com/odordaniel)
