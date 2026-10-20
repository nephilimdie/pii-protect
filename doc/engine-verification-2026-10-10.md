# Verifica locale del motore - 10 ottobre 2026

## Ambito

Codice locale, test unitari e API reale con PostgreSQL 17 temporaneo.
Nessun accesso o rilascio in produzione. Nessun database esistente modificato.
Immagine Docker gia disponibile: `pseudora-cloud-sim-pii-api:latest`, Python 3.11.16.
Il codice API corrente viene montato nell'immagine; non si tratta di una nuova
build delle dipendenze. Cache modelli esistente, download disabilitati.

## Difetti corretti

### Restrizioni dei detector tra elementi batch

`PiiAnonymizer.restrict_layers` intersecava i layer con la selezione del precedente
elemento, anziche con la configurazione iniziale del tenant. Contesti differenti
nello stesso batch potevano lasciare zero layer selezionati. Un contesto senza
restrizioni non ripristinava la selezione iniziale.

La selezione riparte ora da una baseline immutabile. Due test di regressione
riproducevano il problema prima della correzione e passano dopo.

### Surrogati con tenant e PostgreSQL

Le query `ON CONFLICT` di `surrogate_profiles` e `surrogate_mappings` non includevano
il predicato `WHERE tenant_id IS NOT NULL` degli indici parziali della migrazione
051. Con un database migrato da zero, la modalita surrogate restituiva 503.

Le query sono ora allineate agli indici esistenti, senza modificare lo schema.
Quattro test coprono la forma SQL per profili/mapping, con tenant e senza tenant.
La prova reale riproduceva il 503 e passa dopo la correzione.

## Risultati

- 195 test unitari superati nel container.
- Migrazioni da database vuoto e readiness superate.
- Richiesta senza autenticazione respinta con 403.
- Modalita tag e surrogate: nome/email sintetici sostituiti, risposta sicura.
- Ripristino esatto del testo originale in entrambe le modalita.
- Altro tenant e altro progetto non recuperano gli originali.
- Richieste ripetute mantengono lo stesso mapping.
- Test con testo sintetico di 725 caratteri superato.
- Batch con tag e surrogate nella stessa richiesta superato.
- Privacy Filter ONNX e AI4Privacy caricati, come confermato dai log.
- Nessun layer disabilitato dallo script di verifica.

La modifica gia presente che esclude risposte unsafe dagli output batch e stata
conservata e verificata dalla suite unitaria.

## Ripetere il controllo

Dalla root del repository, con Docker avviato, immagine engine gia costruita
e cache modelli popolata:

```sh
python3 scripts/check-engine-local.py \
  --image pseudora-cloud-sim-pii-api:latest \
  --cache-volume pseudora-cloud-sim_pii_hf_cache
```

Immagine e volume sono parametri: usare i nomi presenti sulla propria macchina.
Lo script crea credenziali casuali, una rete dedicata e PostgreSQL in tmpfs.
Espone solo localhost, usa la porta 15679 (modificabile con `--port`) e rimuove
i propri container e la propria rete al termine, anche in caso di errore.
Riutilizza il volume della cache dei modelli senza eliminarlo; il loader puo
materializzare i file ONNX nella cache. Non avvia Cloud, UI, Redis o worker.

## Limiti della verifica

Questi risultati non certificano assenza di falsi negativi o sicurezza completa.
Il testo breve non esercita necessariamente tutti i detector: AI4Privacy salta
per impostazione predefinita testi inferiori a 200 caratteri.

`api/app/reporting/benchmark.py` misura regex dimostrative separate dal motore,
su sette esempi sintetici con nomi anche letterali. Il suo F1 non dimostra
l'accuratezza della pipeline reale. Serve un corpus annotato indipendente,
multilingua, con testi lunghi e casi negativi, eseguito sulla stessa API.

Non sono stati verificati qui: carico concorrente, performance di produzione,
upgrade di database popolati, browser/Cloud, OCR, PDF, gRPC, ogni policy e ogni
permutazione di ACL. L'isolamento controllato riguarda il ripristino tramite API
engine con credenziali interne, non tutta l'autorizzazione utenti del Cloud.

L'ambiente Python locale precedente aveva problemi di librerie native; Python
3.14 locale non era compatibile con SQLAlchemy fissato dal progetto. I risultati
riportati sono quelli ottenuti con Python 3.11 del container.
