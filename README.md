# AI Játékasszisztens – hordozható Windows-verzió (v1.9)

Ez a projekt a működő v1.8-as alkalmazásból készít **PyInstaller onedir, ablak nélküli** Windows EXE-t. Nem készít telepítőt, és nincs szükség Inno Setupra vagy kódaláírásra a *buildhez*. A Windows Smart App Control az aláíratlan EXE-t ettől még blokkolhatja.

## Elkészítés

1. Csomagold ki rövid útvonalra, például `C:\AIJA-Build`.
2. Windows alatt futtasd a `build_portable.bat` fájlt. Ehhez telepített Python 3 és internetkapcsolat szükséges a csomagok letöltéséhez.
3. Sikeres build után a teljes `dist\AIJatekasszisztens` mappát másold a végleges helyére, például `C:\Apps\AIJatekasszisztens`.
4. Indítsd az `AIJatekasszisztens.exe` fájlt. Nem nyílik terminálablak: a program a tálca értesítési területén jelenik meg.
5. Jobb kattintás a tálcaikonon → **Automatikus indítás Windowszal**. Ez csak a jelenlegi felhasználóhoz ad indítási bejegyzést, rendszergazdai jog nem kell.

A hordozható kifejezés a telepítés nélküli futtatást jelenti. A beállítások és előzmények továbbra is a `%LOCALAPPDATA%\AIJatekasszisztens` mappába kerülnek; az API-kulcs a Windows Credential Managerben van. Ezért nem pendrive-ról több számítógépen automatikusan hordozható profil.

## Frissítés

Zárd be a tálcaikon jobb kattintásos **Kilépés** menüpontjával. Cseréld le a program teljes mappáját az új buildre. Ha a hely vagy az EXE neve megváltozik, a tálcaikon jobb kattintásos menüjében kapcsold be újra az automatikus indítást.

## Biztonsági megjegyzések

- A Smart App Control a helyi, aláíratlan buildet is blokkolhatja. Ez a kiadás nem kerüli meg a Windows védelmét.
- Ne helyezd a programot Downloads vagy ideiglenes mappába, ha automatikus indításra használod.
- A felhasználói adatok törlése nem része a program mappájának eltávolításának. Adatmentés előtt ne töröld az AppData mappát.
- Az automatikus indítást a tálcaikon menüjében kikapcsolhatod. A program futását a „Kilépés” opció állítja le.
- A forrás ellenőrizve lett Python-szintaktikailag; az EXE-t itt Linuxon nem lehet Windowsra lefordítani vagy futás közben tesztelni.

## Előzményablak állapota (v1.8)

- A fejléc Előzmények gombja egyértelmű kézi választás: kinyitja/becsukja és megjegyzi az állapotot.
- Az előzmény-gyorsbillentyű és a tálcaikon Előzmények menüpontja a **legutóbbi kézi állapotot** állítja vissza. Ha legutóbb összecsuktad, csak a fordítási panel nyílik meg.
- Területkijelölés és FPS-gyorsfordítás mindig kompakt nézetet mutat, de **nem írja felül** ezt a mentett választást.
- A nézetek külön mentett mérete megmarad. A korábbi beállításokat és fordításokat nem törli a frissítés.


## v1.9 – karbantartási és biztonsági kiadás

- A forrás a működő v1.8-ból származik; a UI, egérgombok, gyorsbillentyűk, előzmények és a mentett ablakállapot változatlan működésűek.
- A konzol nélküli futtatásban hibát okozható `print()` hívások helyett a helyi `hiba.log` fájlba kerülnek a fájlműveleti figyelmeztetések, érzékeny adatok nélkül.
- Eltávolítva a képernyőfigyelés korábbi, már nem használt időzítési beállításai, két fölösleges import és egy kétszeri `thread.join()`. A régi beállításfájlokat a program továbbra is elfogadja.
- Az API hitelesítési hibái esetén nincs felesleges fallback-hívás azonos kulccsal ugyanarra a végpontra. Az API hibaválaszok nyers tartalma nem kerül a felületre.
- Korlátozott maximális JPEG-kérésméret (12 MiB); a válaszmennyiségi korlát, a HTTPS-ellenőrzés, a redirect tiltása és a Windows Credential Manager megmaradt.
- A régi telepítési adatokat nem törli; a konfiguráció és az előzmények a meglévő AppData útvonalon maradnak.

Ez statikus, izolált tesztekkel ellenőrzött forráscsomag; tényleges Windows/PyInstaller végponttól végpontig teszt szükséges. Aláírás nélkül a Smart App Control továbbra is blokkolhatja az új EXE-t.
