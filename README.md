# Pokecawatch Telegram Bot

Bot Telegram che controlla Pokecawatch e notifica le nuove lotterie/prenotazioni di carte Pokémon in Giappone.

Il messaggio inviato contiene:

- Nome espansione
- Luogo/Sito della lotteria
- Data o periodo della lotteria
- Link alla fonte Pokecawatch

## 1. Installazione

```bash
python -m venv .venv
```

Su Windows:

```bash
.venv\Scripts\activate
```

Su macOS/Linux:

```bash
source .venv/bin/activate
```

Poi installa le dipendenze:

```bash
pip install -r requirements.txt
```

## 2. Configurazione

Copia il file `.env.example` e rinominalo `.env`:

```bash
cp .env.example .env
```

Su Windows puoi semplicemente duplicare il file e rinominarlo.

Poi inserisci:

```env
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

## 3. Come ottenere il token Telegram

1. Apri Telegram.
2. Cerca `@BotFather`.
3. Scrivi `/newbot`.
4. Segui le istruzioni.
5. Copia il token nel file `.env`.

## 4. Come ottenere il CHAT_ID

Metodo rapido:

1. Scrivi un messaggio al tuo bot Telegram.
2. Apri nel browser:

```text
https://api.telegram.org/botTOKEN_DEL_BOT/getUpdates
```

3. Cerca il campo `chat` e poi `id`.
4. Inseriscilo in `.env`.

Per un canale Telegram, aggiungi il bot come amministratore e usa come `TELEGRAM_CHAT_ID` il nome del canale, ad esempio:

```env
TELEGRAM_CHAT_ID=@nome_canale
```

## 5. Avvio

```bash
python bot.py
```

Al primo avvio, di default, il bot salva le lotterie già presenti senza inviarle. Questo evita di ricevere decine di notifiche vecchie.

Per notificare anche tutto ciò che trova al primo avvio, imposta nel file `.env`:

```env
SEND_ON_FIRST_RUN=1
```

## 6. Formato notifica

Esempio:

```text
🎯 Nuova lotteria Pokémon TCG JP

📦 Nome espansione:
Abyss Eye / アビスアイ

📍 Luogo lotteria:
Pokémon Center Online

🗓️ Data:
fino al 20/04 alle 16:59 JST

🔗 Fonte:
Pokecawatch
```

## 7. Note importanti

- Il bot monitora la categoria `抽選・予約情報` di Pokecawatch.
- Evita notifiche doppie salvando ogni lotteria in un database SQLite locale.
- La traduzione automatica può non essere perfetta, quindi il messaggio conserva anche il nome originale giapponese.
- Se Pokecawatch cambia struttura HTML, potrebbe essere necessario aggiornare il parser.

## 8. Esecuzione continua

Per tenerlo sempre attivo puoi usare:

- un VPS;
- un Raspberry Pi;
- Docker;
- Railway/Render/Fly.io, se vuoi deploy online.

Nel progetto sono inclusi anche `Dockerfile` e `docker-compose.yml`.
