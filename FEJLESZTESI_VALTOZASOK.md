# Korábbi stabilitási fejlesztések

A 2.0.0 kiadás összefoglalója: [CHANGELOG.md](CHANGELOG.md).

# 1. ütem – stabilitási fejlesztések

Az alap a felhasználó által feltöltött `AI-Jatekasszisztens-main(3).zip`.
A felületet és a fordítás működését nem módosítottuk.

- 11 automatikus regressziós teszt: API URL-biztonság, `/v1/chat/completions`, hotkeyek, ütközések, WIN és egérgombok.
- GitHub Actions: tesztfuttatás a build előtt, mindkét Python-fájl szintaxisellenőrzése.
- Régi beállítások migrációs hibájánál kevesebb személyes adatot tartalmazó naplózás.
- Hiányzó `soundcard` esetén érthetőbb hibaüzenet az eszközlista betöltésekor.
- README és CONTRIBUTING fejlesztői ellenőrzési útmutatója.

## Ellenőrzött meglévő funkciók

- A `/v1/chat/completions` már támogatott volt, ezért nem módosítottuk.
- A `WIN` módosító a natív Windows gyorsbillentyű-kezelőben támogatott; nem tiltottuk.
- A `QLockFile` egy példányos védelme már szerepelt a projektben, ezért nem írtuk át.

## Nem része ennek az ütemnek

- Teljes Windowsos UI/fordítási integrációs tesztek.
- Nagy modulok refaktorálása, új képernyőfelvételi motor.
- Teljes konfigurációs migrációs stresszteszt.

A `requirements.txt` és `requirements-lock.txt` változatlan, új csomag nem szükséges.
