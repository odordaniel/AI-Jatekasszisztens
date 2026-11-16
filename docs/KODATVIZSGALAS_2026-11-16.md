# Kódátvizsgálás – 2026. november 16.

Kiindulás: a #11-es PR beolvasztása utáni `main`,
`f6274ad16284147356e26c2d81796809fb7f9b4f`.

## Átnézett területek

Képi és hangfordítás, API-válaszok feldolgozása, háttérszálak és kilépés,
késleltetett képrögzítés, globális gyorsbillentyűk, ablakfókusz és nézetváltás,
előzmények/mappák mentése és helyreállítása, játékfelismerés, közös beállításstílus,
Windowsos build és függőségrögzítés. Az átnézés nem bizonyítja, hogy minden lehetséges
hiba megszűnt; az alábbi pontokhoz konkrét javítás és ellenőrzés készült.

## Javított hibák

1. **Félbeszakadt mappaátnevezés:** a fordítások fájlja már az új mappanévre
   hivatkozhatott, miközben a mappafájl még a régit tartalmazta. A mappatörlés
   fordításokat megőrző kompatibilitási művelete is érintett volt. Mindkettő
   a módosítás előtti állapotot naplózza a már létező helyreállítási formátumban.
   A napló csak mindkét sikeres mentés után törlődik; sikertelen visszaállítás
   letiltja a további mentést az adatvesztés elkerülésére.
2. **Dupla FPS-rögzítés:** a 200 ms-os várakozás alatt újabb gyorsbillentyű további
   rögzítést ütemezhetett. Most foglaltságjelző és kérésazonosító védi ezt az
   időszakot. Bezárás után a régi időzítő nem hajthat végre újabb felvételt,
   új kérés indításakor sem. Területkijelölés alatt az FPS-parancs nem rögzíti a kijelölőt.
3. **Kilépés aktív háttérmunkával:** a modelllista- és hangeszköz-lekérdezésekre
   eddig nem várt a program. A leállítás minden nyilvántartott QThread befejezését
   ellenőrzi, és megszakítja a függő képrögzítést/előkészítést. Nem támaszkodik
   a szálállapot ellenőrzése után bekötött `finished` jelre. A hangfelvétel nem
   indítható újra leállítás közben, a késői hangjelzések nem nyitnak új felületet.
4. **Korlátlan hangfordítási hibaválasz:** HTTP-hibánál a `response.text[:400]`
   a teljes válasz beolvasása után vágott. A kód most csak a státuszt használja;
   az API-válasz törzse nem kerül a hibaüzenetbe. A sikeres válasz továbbra is
   legfeljebb 256 KiB; az átirányítás kifejezetten elutasított.
5. **Hibás hangfordítási válasz és CA-útvonal:** a JSON `null` eddig `None`
   szövegként sikeres fordításnak számított. Most hibának számít, és a meglévő
   tartalékmodell használható. A szöveges hangfordítás a képi fordítás közös
   URL-ellenőrzését és tényleges AppData/Caddy CA-útvonalát használja. Megszakított
   munkamenet nem indít újabb tartalék API-kérést.
6. **Külön, korlátlan modelllistabetöltő:** a hangfordítás szöveges modelllistája
   most a közös, 2 MiB-ra korlátozott, átirányítást elutasító lekérdezést és
   válaszértelmezőt használja. Megmarad a `models/` előtag levágása.

## Optimalizálás

A leszármazott mappák keresése korábban minden mappánál újra végignézte a teljes
mappalistát. Most egy szülő–gyermek indexből járja be a fát. A darabszámlálás
minden fordításnál végigjárt minden szülőmappát; most egyszer összeszámolja a közvetlen
bejegyzéseket, majd a levelektől a gyökerek felé összesít. Mindkét eljárás iteratív.

Helyi, szintetikus mérés: 10 000 fordítás az 500 szint mély mappafa alján,
három futás legjobb ideje, azonos Python-folyamatban, a régi és új metódusokkal:

| Művelet | Korábban | Javítva |
| --- | ---: | ---: |
| Mappák összesített fordításszáma | 657,40 ms | 1,15 ms |
| Leszármazott mappák keresése | 8,94 ms | 0,11 ms |

Ezek a metódusok futási idejét mutatják, nem a teljes felület vagy API gyorsulását.
A normál, sekélyebb mappafáknál kisebb különbség várható.

## Ellenőrzés és korlátok

- 171 sikeres helyi teszt, a Qt felületi tesztekkel együtt.
- `python -m py_compile src/*.py` sikeres.
- Új hibareprodukciók: megszakított kétfájlos mentés és újraindítás, sikertelen
  visszaállítás, mély mappafa, HTTP-hiba/átirányítás/nagy vagy null válasz,
  helyi CA, API-megszakítás, ismételt és törölt FPS-kérés, aktív szálak melletti kilépés.
- Az új hibatesztek egy korábbi változatát az eredeti forráson is futtattuk:
  a mentési, API- és életciklushibák ott hibás eredményt adtak.
- Nem történt valódi API-hívás, hangfelvétel vagy személyes képrögzítés.
- A Windowsos CI külön futtatja a teljes tesztcsomagot és az EXE építését.
  A valódi játékfókusz, hangkimenet és szolgáltatói API működése további kézi
  Windows-ellenőrzést igényel; a CI önmagában ezeket nem igazolja.
