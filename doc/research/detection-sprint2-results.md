# Detection sprint 2: risultati e criteri di rilascio

## Cosa e' stato completato in locale

- Adattatore Rizzo opzionale: revisione dei pesi obbligatoria, errore su modello
  assente, inferenza fallita, finestre mancanti, score/offset non validi.
- Pipeline: un motore selezionato ma indisponibile non viene saltato in silenzio.
- Regole per CF spezzati con checksum, email offuscate, IPv6 validi, mesi abbreviati,
  campi di nascita e colonne CSV, con offset riferiti al testo originale.
- Filtri contestuali per placeholder, numeri di citazioni della Cassazione,
  date in contesti storici espliciti e parole comuni classificate come telefono.
- Test che un nome incluso in un indirizzo rimanga un indirizzo.
- Cloud: interruttore esistente piu' selezione dei livelli; errori di salvataggio
  non scambiati per successi; traduzioni IT/EN; blocco dell'attivazione tenant se
  il motore non e' attivo sulla piattaforma.
- Snapshot delle immagini engine/OCR prima del rebuild, con manifest e test.
- Documentazione del futuro modello proprietario, senza codice di addestramento.

La regola di nascita richiede un indizio di nascita: una provincia e una data isolate
non bastano, per non trasformare luogo/data di una firma in dati di nascita.
Il caso della slide con "al" ha un test sul falso telefono, ma questo non equivale
a una verifica visiva della slide originale/OCR in produzione.

## Provenienza delle misure

Base Git `7b8b69d` piu' modifiche di questo sprint. I metadati dei runner riportano
la base Git: il codice era ancora nel working tree durante l'esecuzione.
Fingerprint SHA-256 dei sorgenti Python effettivi `api/app`, congelato prima del v2:

`fbba63ed363e24f68aa3ec5f643e21ea5cb086d1e59605aaa983ea525557e79c`

Riproduzione del fingerprint, dalla radice engine:

```sh
find api/app -type f -name '*.py' -print0 | sort -z | xargs -0 shasum -a 256 | shasum -a 256
```

Docker locale, immagine `docjobs-engine:base`, modelli reali, PostgreSQL temporaneo,
endpoint HTTP `/v1/anonymize` con `dry_run=true`, policy `generic_professional`.
Confronti ablation con e senza Rizzo, non testi diversi fra sistemi.
Il dataset v2 e' usato una sola volta per questa valutazione finale; nessun esempio
e' stato aperto per modificare i rilevatori e nessuna taratura seguira' il risultato.

SHA-256 del v2 congelato:
`eff917aaea0d7fe833fcc8989e6d3ef5739ecd1347c44a1c3ad49d720640288d`.

## Definizioni

- **Fughe**: token/parole degli span gold non interamente coperti dalla mascheratura,
  indipendentemente dal tipo. Non e' la percentuale di richieste che perde dati.
- **FP negativi**: span negativi di controllo intersecati da una mascheratura.
  Non e' `1 - precision` e non e' la percentuale di documenti con errori.
- **F1 lenient**: un overlap con tipo compatibile conta come rilevazione; un F1 alto
  non garantisce che ogni carattere personale sia stato coperto.
- **ms/1k**: tempo per mille caratteri a concorrenza uno su questa macchina.
  Non e' un p95/p99 di produzione o una misura della capacita' sotto carico.

## Sviluppo: it_pii_v1, 750 documenti

| Configurazione | Fughe | FP negativi | F1 lenient | ms/1k |
|---|---:|---:|---:|---:|
| Bilanciata, senza Rizzo | 3.9% | 8.0% | 95.5% | 317.0 |
| Bilanciata, con Rizzo | 2.8% | 16.8% | 91.7% | 579.4 |
| Massima, senza Rizzo | 3.4% | 8.4% | 95.4% | 325.4 |
| Massima, con Rizzo | 2.4% | 17.1% | 91.6% | 570.6 |

## Sviluppo: ex heldout v1, 442 documenti

Questo set era gia' stato osservato e discusso: non lo presentiamo come nuovo test
indipendente. Serve a verificare se il guadagno osservato sul primo set si trasferisce.

| Configurazione | Fughe | FP negativi | F1 lenient | ms/1k |
|---|---:|---:|---:|---:|
| Bilanciata, senza Rizzo | 15.7% | 12.2% | 79.6% | 280.9 |
| Bilanciata, con Rizzo | 11.0% | 27.4% | 74.2% | 550.8 |
| Massima, senza Rizzo | 15.3% | 14.6% | 79.1% | 288.7 |
| Massima, con Rizzo | 10.7% | 28.9% | 74.0% | 564.9 |

Le metriche dettagliate e gli intervalli bootstrap sono nei JSON in
`results/detection-sprint2/`. I JSON contengono aggregati, non testi dei documenti.

## Decisione prima del test finale

Rizzo non soddisfa il vincolo per Bilanciata: i FP superano il 15% su entrambi i set.
Per Massima e' un candidato opzionale: riduce le fughe, ma peggiora F1 e latenza e
maschera piu' contenuto innocuo. Non chiamarlo un miglioramento incondizionato.
Build e runtime restano opt-in, anche per la verifica della provenienza dei pesi.

## Test finale: v2 congelato, 426 documenti

| Configurazione | Fughe | FP negativi | F1 lenient | ms/1k |
|---|---:|---:|---:|---:|
| Bilanciata, senza Rizzo | 18.0% | 18.0% | 79.2% | 318.0 |
| Bilanciata, con Rizzo | 12.2% | 30.1% | 76.7% | 544.3 |
| Massima, senza Rizzo | 16.8% | 19.4% | 78.3% | 316.9 |
| Massima, con Rizzo | 11.2% | 30.9% | 76.1% | 554.5 |

Il controllo SHA-256 prima e dopo l'esecuzione coincide; il codice dei rilevatori
non e' stato modificato durante o dopo il test finale.
Sono state eseguite 6.472 richieste nei tre confronti finali (4 configurazioni per
750 + 442 + 426 documenti), oltre alle prove preliminari; non e' un test di carico.

**Decisione finale:** Rizzo soddisfa il criterio di riduzione delle fughe in Massima
su tutti e tre i corpus, ma non il vincolo sui falsi positivi per Bilanciata.
Mantenerlo come opzione esplicita per Massima, con avviso sul maggiore oscuramento;
non accenderlo automaticamente a tutti i clienti. Configurazione standard e build
restano senza Rizzo finche' non viene autorizzata l'attivazione sulla piattaforma.
L'interfaccia permette override consapevoli, non raccomanda Bilanciata con Rizzo.

Rispetto alla Massima senza Rizzo, sul v2 la fuga scende di circa 5.6 punti percentuali,
ma la latenza per mille caratteri cresce circa del 75% e i FP di circa 11.5 punti.
Neppure la configurazione senza Rizzo raggiunge il 15% di FP su questo nuovo set.
Non usare il risultato di sviluppo del 3.9% come promessa commerciale generale.
Un nuovo ciclo di miglioramento richiedera' altri dati di sviluppo e un altro test
finale indipendente: questo v2 e' ora stato valutato e non deve diventare un target.

## Verifiche locali

- Engine unit: 587 passati, 4 saltati, inclusi errore/assenza Rizzo che devono
  raggiungere il router come 503 senza restituire il testo originale.
- Benchmark/scorer/report: 13 passati.
- Cloud PHP: 588 passati, 1 saltato (589 totali).
- Browser del dialogo reale: desktop 1365x900 e mobile 390x844; rifiuto resta aperto,
  successo chiude, nessun overflow o errore JavaScript. Backend intercettato localmente.
- Build frontend riuscita; rimane il warning preesistente sul chunk vendor >800 kB.
- Suite deploy esistente passata, snapshot immagini passato, ShellCheck 0.11 passato.

Non sono stati eseguiti deploy, migrazioni o chiamate di test in produzione.
Non e' stata eseguita una build completa della nuova immagine con download pesi:
le prove reali hanno usato l'immagine ML locale e i sorgenti montati read-only.
La memoria osservata del container con tutti i modelli caricati e' circa 3.4-4.5 GiB;
non e' una misura del picco o del costo incrementale di Rizzo. I benchmark senza
inferenza Rizzo mantenevano comunque il modello caricato per il confronto.

## Riproduzione

```sh
python3 benchmark/italian/run.py \
  --image docjobs-engine:base --cache-volume docjobs-hf \
  --rizzo-model-volume bench-rizzo-model \
  --dataset benchmark/italian_heldout_v2/dataset/it_pii_heldout_v2.jsonl \
  --systems ablation_no_rizzo,ablation_with_rizzo,ablation_no_rizzo_maximum,ablation_with_rizzo_maximum \
  --reference ablation_no_rizzo --out /tmp/pseudora-sprint2-final-v2 --port 15791
```

I nomi di immagine/volumi sono quelli locali usati, non prerequisiti universali.
Per futuri tuning usare nuovi dati di sviluppo; non riutilizzare il v2 come prova
indipendente dopo aver adattato il codice ai suoi risultati.
