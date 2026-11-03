# Rizzo-PII: integrazione opzionale e metodologia

## Decisione del 2 novembre 2026

Non addestriamo un modello Pseudora in questo sprint. Non introduciamo training,
raccolta di documenti dei clienti o infrastruttura GPU. Un modello proprietario e'
una possibilita' futura, subordinata a dati autorizzati, budget e risultati misurabili.

Rizzo non sostituisce i controlli esistenti: e' un motore aggiuntivo opzionale.
L'integrazione mantiene regex, Presidio, Privacy Filter e AI4Privacy e usa lo stesso
merger, policy e soglie della pipeline. Non equivale a una garanzia di rilevare ogni PII.

## Versione studiata

- Codice: https://github.com/Rizzo-AI-Academy/rizzo-pii
  commit `9057eeff88bdf0444e5d3361cf0766b60c5b8a95`.
- Pesi: https://huggingface.co/rizzoaiacademy/rizzo-pii-0.3B
  revisione `a1c3c83827eca22e9675e30c1111c4641caf5901` (v1.5.0).
- Model card della revisione:
  https://huggingface.co/rizzoaiacademy/rizzo-pii-0.3B/blob/a1c3c83827eca22e9675e30c1111c4641caf5901/README.md

La documentazione descrive un token classifier mmBERT di circa 0.3B parametri,
etichette BIO e dati italiani per entita' personali. La pipeline raggruppa i token
in span. Il nostro adattatore usa finestre di 120 parole con sovrapposizione di 20,
riporta gli offset al testo originale e fonde gli span sovrapposti.
Le categorie organizzazione, importo, ora, eta' e genere non diventano automaticamente
PII da mascherare. Nomi, identificativi e frammenti di indirizzo sono mappati sulle
categorie del motore. La scelta delle categorie influenza precisione e recall.

Il model card dichiara MIT. Questo non basta a concludere che ogni dataset a monte
abbia gli stessi termini: i riferimenti ai dati includono condizioni differenti,
fra cui attribuzione, termini Llama e fonti senza licenza chiaramente documentata.
Prima della redistribuzione commerciale dei pesi serve una verifica della provenienza.
Il build standard non li scarica; non presentare questa nota come parere legale.

## Come si replicherebbe in futuro

1. Definire categorie, confini degli span e convenzioni di annotazione.
2. Raccogliere solo dati sintetici o esplicitamente autorizzati, con registro delle
   licenze, provenienza e consensi. Mai usare automaticamente richieste dei clienti.
3. Separare train/dev/test per sorgente, template e persone, prima di addestrare.
4. Allineare etichette BIO ai subword, gestire troncamento e sovrapposizione; verificare
   che maiuscole/minuscole e augmentation non facciano contaminare il test.
5. Addestrare il token classifier, selezionare soglie esclusivamente su dev e
   misurare l'effetto combinato nella pipeline, non solo il modello isolato.
6. Misurare fuga residua, precision/recall/F1, falsi positivi sui negativi, latenza
   e memoria; pubblicare limiti, versioni, revisioni dei dati e risultati riproducibili.

Questi passaggi sono documentazione futura: nessun job di training e' previsto ora.

## Protocollo di valutazione

- `italian/dataset/it_pii_v1.jsonl`: sviluppo.
- `italian_heldout/dataset/it_pii_heldout_v1.jsonl`: ora sviluppo, essendo gia' stato
  consultato negli sprint precedenti; non chiamarlo test indipendente finale.
- `italian_heldout_v2/dataset/it_pii_heldout_v2.jsonl`: test finale congelato.
  Non leggere gli esempi, cambiare gold o tarare soglie dopo aver visto il risultato.

Confrontare stessa policy e stesso codice con/senza Rizzo, a entrambi i livelli.
Riportare i falsi positivi con il denominatore del benchmark (span negativi), non
confonderli con quota di documenti o di richieste. I due corpus di sviluppo non
dimostrano automaticamente generalizzazione a documenti reali dei clienti.

Criteri concordati: Massima solo se riduce le fughe; Bilanciata solo se riduce le
fughe e i falsi positivi restano circa entro il 15%. Se non aiuta resta spento.
Il default conservativo resta disabilitato finche' il confronto e' completo.

## Installazione e sicurezza

Build opzionale `--build-arg INCLUDE_RIZZO=true`; runtime
`DETECTION_LAYERS__RIZZO__ENABLED=true`. Il percorso predefinito e'
`/opt/models/rizzo-pii-0.3B-v1.5.0`. Un mount esterno deve includere `REVISION` con
la revisione esatta; non basta rinominare una directory di pesi sconosciuti.
I pesi non si scaricano durante una richiesta. Il modello si carica all'avvio.

Un motore selezionato ma indisponibile, un errore di inferenza o una risposta
incompleta devono fallire, non trasformarsi in una lista vuota di PII. In produzione
usare `FAILURE_MODE=closed`. La readiness controlla i motori abilitati sulla piattaforma.
La UI tenant non puo' caricare pesi o abilitare un motore spento dalla piattaforma.
Una volta installato e abilitato, puo' selezionare attivazione e livelli per tenant.
Le policy che selezionano esplicitamente un layer prevalgono sul gate di livello,
ma non possono superare una disabilitazione tenant.

## Rilascio

Il deploy resta un passaggio separato da autorizzare. Conservare immagine precedente,
backup DB e configurazione precedente. Non ripristinare automaticamente un database
su cui possono essere arrivate scritture. Verificare readiness, richieste normali e
con errori, isolamento tenant, RAM a caldo e latenza prima di eliminare i rollback.
