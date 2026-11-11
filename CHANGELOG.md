# Változások

## 2.0.0 – 2026-11-11

### Új funkciók
- Játékhang rögzítése és magyar fordítása; beszédátírás, időbélyegek és beszélőjelölések a hangfordítási folyamatban.
- Offline játékfelismerés a Windows aktív folyamatából és helyi Steam/Epic adatokból; kézi EXE–játék párosítás. Nem használ képalapú AI-játékfelismerést.
- Előzmények fájlkezelő jellegű műveletei: mappák, jobb kattintás, Ctrl/Shift többes kijelölés, másolás, beillesztés, átnevezés, áthelyezés és törlés.

### Javítások és optimalizálások
- Kép- és hangfordítás mappához rendelésének egységesítése játékváltáskor; ismeretlen játéknál rendezetlen mentés.
- Törölt játék-mappa újralétrehozása következő mentéskor, amennyiben a játék felismerhető.
- Képernyőkivágás, hangfeldolgozás és előzménylista teljesítményének célzott javításai.
- Hibás konfiguráció kezelése és párhuzamos helyi mentések védelme.
- Regressziós tesztek bővítése a mentés, játékfelismerés és fordítási életciklus területén.

### Kiadás
- Alkalmazásban megjelenített verzió: `2.0.0`.
- Kiadási Git-tag: `v2.0.0`. A GitHub Actions a tag közzétételekor készíti el a Windows-portable ZIP-et és a SHA-256 ellenőrzőösszeget.
- A Windowsos EXE digitális aláírása jelenleg nincs kész; a Windows védelmi funkciói figyelmeztethetnek.

Megjegyzés: a teljes Windowsos futtatási és kiadási ellenőrzést a tag közzététele előtt célszerű elvégezni.
