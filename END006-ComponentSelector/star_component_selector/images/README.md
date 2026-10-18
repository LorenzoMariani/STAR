# Immagini dei componenti

Un file PNG per componente del catalogo, nominato `Venditore-NomeComponente.png` (es. `SimeraSense-TriScape50.png`).

**Fonte di ogni immagine** (tutte scaricate il 2026-10-13 da documenti e pagine pubbliche dei fornitori):
- [manifest.csv](manifest.csv): per ogni file, l'URL dell'immagine (o del PDF con `#page=N`), la pagina o il documento di origine, il tipo, la data e le dimensioni;
- i metadati del PNG (`Source`, `Description`, `Copyright`), leggibili con un qualunque visualizzatore di proprieta' dei file o con Pillow (`Image.open(f).text`);
- il campo `image` di ciascun componente in `data/catalog.json` (stesse informazioni).

**Diritti:** le immagini sono di proprieta' dei produttori e sono qui solo come riferimento visivo dei prodotti scelti. Per usi diversi (articoli, presentazioni, siti pubblici) serve il permesso del produttore.

**Limiti noti:**
- Dove il fornitore pubblica una sola foto per una famiglia (varianti RGB/MS/HS, taglie 3U/6U, batterie OPTIMUS, motherboard Pumpkin con PPM diversi, XACT-15/50/100...) la stessa immagine e' ripetuta con i nomi dei singoli componenti; la colonna `nota` del manifest lo segnala.
- Nessuna immagine pubblica trovata per Satlantis iSIM-170 e iSIM-170 (SWIR): i file non esistono.
- Le immagini estratte dai datasheet PDF sono a bassa risoluzione (Pumpkin, ISIS); quelle di QUASAR-STRX (sistema in un 1U) e GRAPHIUM (strumento con operatori) sono illustrative.
- Le immagini sono ridotte a un massimo di 1000 px sul lato lungo.
