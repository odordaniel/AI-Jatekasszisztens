# SignPath Foundation – jelentkezési és aláírási terv

## Jelenlegi állapot
Ez a repository-előkészítő csomag **nem tartalmaz aláírt EXE-t**, és nem állítja, hogy a SignPath Foundation jóváhagyta a projektet. A GitHub Actions workflow csak **aláíratlan** Windows-buildet készít. A program kódja és a meglévő buildszkriptek nem változtak.

## Következő lépések
1. A közzététel előtt végezz titok- és személyesadat-ellenőrzést. A korábbi commitokban se legyen titok.
2. Válassz OSI által jóváhagyott licencet, miután megerősítetted a kód tulajdonjogát és ellenőrizted a függőségek licenceit. Szándékosan nincs előre választott LICENSE.
3. Hozz létre nyilvános GitHub repositoryt, és töltsd fel a projekt tartalmát (a projektmappa tartalmát, ne a külső gyűjtőmappát).
4. Futtasd a Windows portable build workflow-t; ellenőrizd a letöltött aláíratlan artifact működését és a függőségek eredetét.
5. Dokumentáld a kiadást, a projekt fenntartását és a buildfolyamatot. A Foundation feltételeit a jelentkezés előtt ellenőrizd: https://signpath.org/ .
6. Jelentkezz a SignPath Foundation ingyenes open-source programjába. A jóváhagyás nem automatikus.
7. Jóváhagyás után, a kapott konkrét SignPath-szervezet/projekt/artifact-konfigurációval készíts hitelesített aláírási workflow-t. Addig **ne** használj fiktív azonosítókat vagy aláírásnak nevezett unsigned ZIP-et.
8. Az aláírt artifactot ellenőrizd Windows alatt, például `Get-AuthenticodeSignature` paranccsal. A Smart App Control elfogadása nem garantált.

## Build-biztonsági következő fejlesztések
- Pineld a GitHub Actions actionöket teljes commit SHA-ra.
- Használj pontosan rögzített, hash-ellenőrzött Python dependency lockfile-t.
- Állíts be branch protectiont, minimális workflow jogosultságokat, és ellenőrzött kiadási folyamatot.
- A SignPath követelményei szerint igazold a forráskód és a build artifact összetartozását.

## Figyelmeztetés
A GitHub Actions artifact és a GitHub Release nem ugyanaz. A workflow nem teszi közzé automatikusan a programot, és nem írja alá. Ne publikálj korábbi személyes konfigurációkat vagy API-kulcsokat.
