# Roadmap: AI Privacy Gateway

## Implementation status (September 2026)

The provider proxy, secrets and prompt-injection checks, OpenAI and Anthropic
stream buffering, OpenAI Responses support, tenant-scoped controls,
per-tenant DEKs, erasure and key rotation are implemented in the corresponding
repositories. Remaining release gates are provider integration tests, an
independent penetration test, broader authorized quality datasets and the
optional document/image plugin.
← [Roadmap principale](roadmap.md) · [README](../README.md)
## Obiettivo
Trasformare `pii-protect` da motore HTTP per rilevazione e pseudonimizzazione PII in un AI Privacy Gateway utilizzabile senza modificare il codice delle applicazioni che chiamano un provider LLM.
L'obiettivo di prodotto e' permettere questo flusso:
```text
Applicazione o SDK
        |
        v
Pseudora Gateway
        |
        +--> autenticazione, tenant, team e policy
        +--> rilevazione PII, segreti e prompt injection
        +--> anonimizzazione o blocco
        +--> provider OpenAI, Anthropic o compatibile
        +--> scansione della risposta
        +--> deanonymization controllata
        |
        v
Applicazione
```
La promessa commerciale deve essere concreta:
> Cambia il base URL del tuo client LLM: Pseudora protegge automaticamente richieste e risposte.
Il motore attuale resta il componente di detection e policy. Il gateway e' un livello applicativo sopra il motore, non una riscrittura del motore.
## Stato di partenza
### Gia' disponibile nel core
- Pipeline a quattro layer: Presidio/spaCy, Privacy Filter, AI4Privacy e regex configurabili.
- Rilevazione di circa 33 categorie PII con strategie surrogate configurabili.
- Modalita' `tag`, `surrogate`, `mask`, `remove` e `block`.
- Mapping reversibile cifrato e supporto a chiavi per tenant.
- Endpoint REST per `anonymize`, `deanonymize`, `detect`, `mask` e batch.
- Policy, context type, versioni, reclassification e scoped configuration.
- API key con ruoli, scadenza, limiti di richieste e limiti di caratteri.
- Tenant ID, isolamento delle configurazioni e audit log.
- Retention, cancellazione dei mapping e procedure di erasure.
- UI amministrativa per configurare layer, tipi PII, regex, policy e statistiche.
- Plugin foundation e direzione marketplace gia' documentate.
- Deployment Docker e funzionamento self-hosted senza dipendenza obbligatoria dal cloud.
### Gap principale
Il client deve oggi conoscere e orchestrare separatamente anonimizzazione, chiamata LLM e deanonymization. Manca un endpoint compatibile con i protocolli dei provider che esegua questa orchestrazione in modo trasparente.
### Limiti da dichiarare
- Il core e' principalmente text-first.
- Il supporto immagini/OCR non e' ancora disponibile.
- La scansione di tool call, function arguments e contenuti multimodali deve diventare esplicita.
- Il motore non e' ancora un router provider con fallback e controllo costi.
- La detection di secrets e prompt injection non costituisce ancora un modulo completo di AI security.
## Principi architetturali
### Separazione delle responsabilita'
1. `pii-protect` resta responsabile di detection, policy, mapping, surrogate, audit tecnico e configurazione engine.
2. `pii-protect-cloud` resta responsabile di identita', provisioning, billing, quote commerciali e gestione tenant cloud.
3. Il gateway applica il protocollo provider, orchestration request/response, routing e controllo del flusso.
4. I plugin estendono funzionalita' opzionali come OCR, nuovi detector e connettori, senza introdurre dipendenze cloud nel core.
### Contratti stabili
Il gateway deve dipendere da interfacce, non da repository o moduli interni del motore. Il contratto minimo del motore deve includere:
- input testuale strutturato;
- lista di span con tipo, offset e confidence;
- trasformazione applicata;
- mapping reference non reversibile esposto al gateway;
- identificativo di contesto;
- tenant e policy version usati;
- stato `safe` e motivazione di eventuale blocco;
- metriche tecniche senza contenuto originale.
Nessun log deve contenere testo originale, valori PII, API key o prompt completo.
## Fase P0: gateway OpenAI-compatible
**Priorita': bloccante per il posizionamento del prodotto**
### Funzionalita'
Implementare almeno:
```text
POST /v1/chat/completions
```
Il contratto deve accettare i campi standard del client OpenAI e preservare i campi non gestiti dal gateway. Il gateway deve supportare almeno:
- `model`;
- `messages`;
- `temperature`;
- `max_tokens` o equivalente;
- `stream`;
- `tools` e `tool_choice`;
- `response_format`;
- metadati compatibili con gli SDK comuni.
### Pipeline request
1. Validare API key e identificare tenant, utente e team.
2. Risolvere policy, context type e provider consentito.
3. Estrarre solo le parti testuali scansionabili preservando la struttura JSON.
4. Applicare detection e policy del motore.
5. Bloccare la richiesta se il motore non e' raggiungibile o se una policy richiede il blocco.
6. Inviare al provider soltanto il payload protetto.
7. Conservare nel vault temporaneo il mapping necessario alla risposta.
8. Registrare audit con conteggi e tipi, mai con valori o prompt.
### Pipeline response
1. Ricevere la risposta dal provider.
2. Verificare che la risposta sia valida e coerente con il protocollo.
3. Scansionare testo, tool call e JSON generato dal modello.
4. Bloccare o redigere PII/secrets eventualmente creati dal modello.
5. Ripristinare i valori originali solo se la policy del tenant lo consente.
6. Restituire la risposta con lo schema originale e metadati tecnici minimali.
7. Eliminare il mapping temporaneo secondo retention e policy.
### Criteri di accettazione
- Un'applicazione OpenAI SDK funziona cambiando soltanto `base_url` e API key.
- Il provider non riceve mai il valore originale in una richiesta protetta.
- Il client riceve una risposta deanonymized quando la policy lo permette.
- Una risposta del modello che contiene nuovo PII viene bloccata o redatta.
- Un errore del motore non inoltra il prompt in chiaro.
- Sono supportati retry idempotenti e timeout espliciti.
- Il comportamento e' testato con un provider mock che registra il payload ricevuto.
## Fase P0: streaming e struttura dei messaggi
Lo streaming non deve essere trattato come una semplice concatenazione di stringhe.
### Requisiti tecnici
- Buffer per placeholder divisi tra due chunk.
- Flush sicuro alla chiusura dello stream.
- Preservazione di SSE, `data:`, `[DONE]` e usage.
- Supporto a piu' choices e delta parziali.
- Supporto a tool call trasmesse a frammenti.
- Timeout separati per connessione, first byte e inattivita'.
- Cancellazione del mapping quando il client interrompe la connessione.
### Test obbligatori
- Placeholder diviso in due, tre e piu' frame.
- Chunk con caratteri UTF-8 divisi.
- Risposta contenente JSON parziale.
- Tool call con argomenti parziali.
- Interruzione client a meta' stream.
- Errore provider dopo l'invio della richiesta protetta.
## Fase P0: sicurezza dei contenuti non testuali
Il gateway deve definire una policy esplicita per ogni parte di una richiesta:
| Contenuto | Comportamento iniziale |
|---|---|
| Testo semplice | Scansiona e trasforma |
| Array `content` | Scansiona ogni blocco testuale |
| Tool/function arguments | Scansiona JSON e stringhe |
| Tool/function results | Scansiona prima dell'invio al modello |
| Immagine | Blocca o passa solo se la policy lo autorizza esplicitamente |
| URL remoto | Non scaricare di default; policy opt-in |
| File allegato | Blocca fino a quando non esiste il modulo documentale |
Il comportamento predefinito deve essere fail-closed per contenuti non supportati, evitando che il gateway dia una falsa impressione di copertura.
## Fase P1: provider Anthropic e adapter
Implementare:
```text
POST /v1/messages
```
La logica di protezione deve essere condivisa. Solo adapter e serializer devono essere specifici del provider.
### Adapter interface
```text
ProviderAdapter
  supports(request)
  extract_scannable_content(request)
  rebuild_request(request, protected_content)
  parse_response(response)
  rebuild_response(response, restored_content)
  stream_decoder()
```
Non duplicare la logica di detection in ogni adapter.
Successivamente aggiungere adapter per provider compatibili OpenAI, Azure OpenAI, Gemini, Mistral e gateway LiteLLM quando esiste una domanda reale da parte degli utenti.
## Fase P1: secrets e prompt injection
### Secrets detection
Creare un registro di recognizer separato dalle PII, con test di validita' e falsi positivi per ogni pattern:
- API key OpenAI, Anthropic e Google;
- AWS access key e secret key;
- GitHub token;
- Slack webhook;
- JWT;
- private key PEM;
- password in URL e configurazioni;
- database connection string;
- cloud credentials e bearer token;
- credenziali nei log applicativi.
La policy deve poter scegliere tra `allow`, `warn`, `redact` e `block` per categoria.
### Prompt injection
Il modulo deve produrre un risultato distinto dalla PII:
```json
{
  "risk_type": "prompt_injection",
  "score": 0.91,
  "action": "block",
  "rule_id": "system_prompt_extraction"
}
```
Non presentare una detection euristica come garanzia assoluta. Documentare confidence, limiti e possibilita' di override amministrativo.
## Fase P1: routing e affidabilita' provider
Il gateway cloud deve permettere di scegliere il provider senza cambiare il client.
### Funzioni
- Provider registry con endpoint, modello, regione e stato.
- Segreti provider conservati in secret manager o cifrati, mai nel database in chiaro.
- Timeout, retry con backoff e circuit breaker.
- Failover solo verso provider autorizzati dalla policy.
- Limiti di token e caratteri per tenant, utente e team.
- Budget mensile e alert di consumo.
- Routing esplicito nella prima versione.
- Smart routing basato su prezzo/latenza solo dopo metriche affidabili.
La versione self-hosted deve poter usare i propri provider key senza obbligare il cliente a Pseudora Cloud. Il cloud puo' offrire gestione centralizzata, routing e reporting come valore commerciale aggiuntivo.
## Fase P1: SDK e adozione
Pubblicare pacchetti minimali e documentati:
- `pseudora-python`;
- `pseudora-js` o `pseudora-typescript`;
- esempi PHP/Laravel;
- configurazione OpenAI SDK con `base_url`;
- integrazione MCP;
- integrazione VS Code;
- integrazione browser extension;
- middleware LangChain;
- transformer LlamaIndex.
Ogni SDK deve includere:
- timeout sicuri;
- retry controllabili;
- errori tipizzati;
- supporto sync e async dove appropriato;
- propagazione di `tenant`, `team` e `context_id`;
- nessun logging automatico del contenuto originale.
## Fase P1: benchmark e quality gate
Creare una suite riproducibile con dataset sintetico e dataset autorizzato anonimizzato.
### Metriche detection
- precision, recall e F1 per tipo PII;
- macro e micro average;
- confidence calibration;
- falsi positivi per pagina e per 1.000 caratteri;
- risultati per lingua e context type.
### Metriche gateway
- latency detection p50/p95/p99;
- time to first byte;
- durata completa richiesta;
- throughput a 1, 4, 8 e 16 richieste concorrenti;
- RAM e CPU per layer;
- error rate per provider;
- percentuale di richieste bloccate;
- percentuale di PII arrivata al mock provider: obiettivo zero.
### Quality gate CI
Una release non deve essere pubblicata se:
- un valore PII raggiunge il provider mock;
- il fail-closed non funziona;
- il round-trip non ripristina correttamente il mapping;
- p95 supera la soglia dichiarata senza aggiornare la documentazione;
- un tenant puo' leggere mapping, policy o audit di un altro tenant.
## Fase P1/P2: immagini, OCR e documenti
Implementare come plugin opzionale per non appesantire il core:
1. OCR di PNG, JPEG e pagine PDF.
2. Coordinate dei token OCR.
3. Riutilizzo della pipeline testuale esistente.
4. Redazione delle aree corrispondenti.
5. Detection di volti, firme e altri dati biometrici con modulo separato.
6. Output immagine e sidecar JSON con tipo, coordinate e confidence.
7. Limiti di dimensione, DPI, pagine e tempo CPU.
8. Rimozione dei file temporanei dopo l'elaborazione.
Endpoint candidato:
```text
POST /v1/anonymize/image
POST /v1/anonymize/document
```
Non dichiarare supporto immagini prima di avere testato screenshot, scansioni con bassa qualita', testo ruotato, piu' lingue e falsi positivi.
## Multi-tenancy e autorizzazione gateway
Il gateway deve risolvere il contesto in questo ordine:
1. credenziale autenticata;
2. tenant associato alla credenziale;
3. team richiesto e autorizzato;
4. policy del team;
5. override dell'utente, se autorizzato;
6. policy globale come fallback.
Il client non deve poter scegliere arbitrariamente un tenant tramite solo header. `X-Pii-Tenant-Id` e' un contesto interno e deve essere validato dal cloud o da una credenziale firmata.
Ogni audit e ogni usage event deve includere identificativi non sensibili di:
- tenant;
- team;
- utente o client;
- provider e modello;
- policy version;
- request id;
- esito e latenza.
Mai includere prompt, risposta, mapping o valore originale.
## Modello business
### Self-hosted open core
Il core puo' restare installabile autonomamente e includere detection, policy, UI admin, plugin foundation e marketplace client. Questo facilita adozione tecnica e fiducia.
### Cloud managed
Il cloud deve vendere principalmente riduzione dell'operativita':
- gateway pubblico;
- tenant e team pronti;
- gestione chiavi;
- routing provider;
- quote e billing;
- audit e retention centralizzati;
- monitoraggio;
- aggiornamenti;
- supporto;
- integrazioni gestite.
### Packaging suggerito
| Piano | Utente ideale | Valore principale |
|---|---|---|
| Free/Beta | singolo sviluppatore | test limitati, un team, provider configurato dal cliente |
| Team | piccole squadre | piu' utenti, policy condivise, audit e quote |
| Business | aziende | SSO, piu' team, routing, retention e supporto |
| Enterprise | organizzazioni regolamentate | isolamento dedicato, SLA, VPC, SIEM e assistenza |
Non vendere inizialmente la semplice quantita' di chiamate. Vendere il controllo del rischio e il tempo operativo risparmiato. Il consumo resta una metrica per i limiti e per evitare costi non controllati.
### Metriche business
- tempo dal signup alla prima richiesta protetta;
- percentuale di utenti che configurano almeno un client;
- richieste protette per account attivo;
- retention a 7, 30 e 90 giorni;
- numero di team attivi;
- provider e modelli piu' usati;
- PII e secrets bloccati;
- costo infrastrutturale per richiesta;
- ticket per account;
- conversione beta verso piano pagante.
## Piano di rilascio
### Milestone 1: Gateway MVP
- OpenAI-compatible request/response.
- Provider mock e un provider reale.
- Fail-closed.
- Tag e surrogate.
- Mapping response-side.
- Audit senza contenuto.
- Test multi-tenant.
- Documentazione quickstart.
### Milestone 2: Produzione controllata
- Streaming stabile.
- Tool call e JSON.
- Timeout e circuit breaker.
- Rate limit gateway.
- SDK Python e TypeScript.
- Dashboard provider, latenza e uso per team.
- Alert operativi.
### Milestone 3: AI security
- Secrets registry.
- Prompt injection module.
- Policy separate per PII, secret e injection.
- Response scanning.
- Red-team test suite.
### Milestone 4: Enterprise adoption
- Anthropic adapter.
- SSO/OIDC.
- SIEM/webhook.
- Data residency.
- KMS/secret manager.
- SLA e runbook.
### Milestone 5: Multimodalita'
- OCR plugin.
- Image redaction.
- PDF/document pipeline.
- Test e limiti operativi.
## Definition of Done per il gateway
Il gateway e' pronto per una beta pubblica quando:
- un utente puo' collegare un SDK senza scrivere codice di orchestrazione;
- il provider non vede PII non protetta in nessun percorso supportato;
- richieste e risposte streaming sono coperte da test;
- tenant e team non possono accedere ai dati reciproci;
- i fallimenti sono chiusi e osservabili;
- esistono benchmark ripetibili;
- il costo per richiesta e' misurato;
- la documentazione dichiara chiaramente cosa non viene scansionato;
- esiste un runbook per provider down, motore down, chiavi compromesse e cancellazione dati;
- il percorso beta verso un piano Team e' comprensibile senza intervento manuale del fondatore.
## Decisioni da prendere prima dell'implementazione
1. Gateway nel cloud privato o modulo distribuibile anche self-hosted.
2. Provider supportati nella prima milestone.
3. Politica di default per tool call e immagini non supportate.
4. Durata massima del vault temporaneo.
5. Gestione delle chiavi provider: secret manager, env o entrambe.
6. Restituzione automatica dei valori reali nelle risposte.
7. Soglie di latenza pubblicate per ogni layer.
8. Confine tra funzionalita' core e funzionalita' cloud premium.
La decisione architetturale raccomandata resta: motore condiviso e tenant-aware, gateway e funzioni commerciali nel cloud, con un adapter self-hosted opzionale per chi vuole eseguire tutto localmente.

## Riferimenti comparativi

- [Piast Gate](https://github.com/vissnia/piast-gate): gateway con masking, ripristino e provider switching; dichiara limiti su immagini, tool call e function arguments.
- [pii-proxy](https://github.com/daslabhq/pii-proxy): proxy locale con dati sintetici plausibili, mapping reversibile e detector regex piu' LLM locale.
- [Cordon](https://github.com/askalf/cordon): gateway OpenAI/Anthropic con fail-closed, streaming, audit hash-chain e vault per richiesta.
- [AI Privacy Gateway](https://github.com/Ciprian-LocalPulse/ai-privacy-gateway): reverse proxy asincrono policy-driven con masking, tokenizzazione e re-identification.
- [Occludra Gateway](https://github.com/occludra/gateway): proxy AI security con PII, secrets, prompt injection e routing provider.

Questi progetti non sono tutti superiori al core: il confronto evidenzia soprattutto la necessita' di aggiungere il livello gateway e le integrazioni provider sopra le capacita' gia' presenti in `pii-protect`.
