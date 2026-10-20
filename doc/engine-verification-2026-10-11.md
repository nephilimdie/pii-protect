# Verifica locale aggiuntiva - 11 ottobre 2026

## Correzioni e verifica

Conservate le correzioni del 10 ottobre (baseline detector per elemento batch e
indici parziali PostgreSQL dei surrogati), con tutti i relativi test.

Nuove correzioni:

1. Privacy Filter elaborava solo i primi 512 token di ogni riga. Ora usa finestre
   sovrapposte di 64 token, batch limitati e deduplicazione degli span identici.
   I test verificano 1.100 token, offset globali e assenza di duplicati.
2. AI4Privacy usa stride 64 per elaborare anche le finestre successive.
3. Presidio, Privacy Filter e AI4Privacy non convertono piu' gli errori di inferenza
   in risultati vuoti. La failure policy puo' quindi bloccare la richiesta.
   Un test percorre detector reale con inferenza simulata in errore, orchestratore
   e handler: risposta 503, safe=false, nessun originale nella risposta.
4. Default min_chars=0 per entrambi i layer neurali. I testi brevi possono contenere
   PII; il precedente default 200 lasciava un nome inglese non protetto nel corpus.
   Gli override espliciti del database restano invariati. Non cambiate soglie score.
5. Espansione confini Unicode, compresi caratteri combinanti: un indirizzo email
   accentato non lascia piu' la lettera iniziale fuori dalla sostituzione nel caso
   verificato. Nessuna regex basata sul nome del caso di test.
6. Nuovo evaluator sull'API reale, per span e non soltanto per tipi. Benchmark demo
   etichettato esplicitamente come tale anche in CI; rimossa la falsa indicazione
   che esercitasse una policy o un anonymizer reali.

## Test eseguiti

- Suite unitaria finale: 213 passati, ripetuta due volte nello stesso container.
- Tre esecuzioni reali durante la verifica, ciascuna con PostgreSQL temporaneo.
- Ultima esecuzione tramite `make benchmark-engine`: superata, F1 minimo 0.90.
- Tag, surrogate, ripristino esatto, ripetizione dei mapping, batch misto,
  richiesta senza credenziali respinta, isolamento ripristino tenant/progetto.
- Modelli Presidio, Privacy Filter ONNX e AI4Privacy caricati; controllati dallo
  script, non dedotti soltanto dall'endpoint readiness.
- Nessun container di test lasciato attivo. Nessuna produzione modificata.

Ambiente: Docker locale con immagine preesistente Python 3.11.16, codice API locale
montato, modelli cached, download disabilitati, PostgreSQL 17 su tmpfs. Non e' una
verifica di una nuova build completa delle dipendenze o di upgrade di dati storici.

## Risultati del corpus sintetico

14 esempi, 14 span annotati, quattro tipi principali (EMAIL, PERSON, IBAN,
FISCAL_CODE). IT/EN, negativi, Unicode e righe lunghe.

| Misura | Prima delle correzioni a testi brevi/Unicode | Dopo |
| --- | --- | --- |
| Veri positivi | 12 | 14 |
| Falsi positivi | 2 | 1 |
| Falsi negativi | 2 | 0 |
| Precision | 85,71% | 93,33% |
| Recall | 85,71% | 100% |
| F1 exact-span | 85,71% | 96,55% |

La prima misura era gia' successiva all'introduzione delle finestre lunghe.
Non rappresenta quindi un confronto completo col codice del 10 ottobre.

Ultima esecuzione: p50 circa 51 ms; p95/p99 circa 1,46 s. Sono 14 richieste locali
sequenziali di lunghezze diverse, non uno stress test o una promessa di latenza.

## Limite ancora visibile

Rimane un falso positivo PERSON sul prefisso "Contatto" nel caso sintetico con
riga molto lunga. Il dato email viene protetto. Non e' stata inserita una denylist
ad hoc per far risultare perfetto il benchmark: serve validazione su corpus piu'
ampio prima di modificare soglie o regole linguistiche.

Questo corpus e' stato usato nello sviluppo, non e' un holdout indipendente. Zero
falsi negativi QUI non significa zero falsi negativi nel prodotto. Restano fuori
da questo controllo: OCR/PDF, estensioni browser e VS Code, contratti provider AI,
carico concorrente, tutte le lingue/policy e tutte le ACL del Cloud.

Ripetizione e formato del dataset: [benchmark README](../benchmark/README.md).
I test completi richiedono di montare il repository intero, non solo `api`, per
importare anche l'evaluator da `benchmark/evaluate.py`.
