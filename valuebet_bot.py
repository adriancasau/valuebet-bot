#cosas a cambiar:
#2. Calcular valuebets con valor esperado
#3. Cambiar normalización de spreads y totals, las acabadas en entero normalizar teniendo en cuenta la probabilidad de clavar el numero
#8. Añadir calculo surebets

import requests
import json
import schedule, time
from datetime import datetime, timezone
from statistics import median

import re
import gspread
from google.oauth2.service_account import Credentials

# --- CONFIG ---
SERVICE_FILE = "service_account.json"   # tu JSON de la service account
SPREADSHEET_ID = "GOOGLE_SHEET_ID"       # el ID del Google Sheet
WORKSHEET_NAME = "Data"                # nombre de la pestaña


def guardar_gsheets(texto):
    # --- AUTORIZACIÓN ---
    SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_file(SERVICE_FILE, scopes=SCOPES)
    gc = gspread.authorize(creds)
    # Abre la hoja
    sh = gc.open_by_key(SPREADSHEET_ID)
    try:
        ws = sh.worksheet(WORKSHEET_NAME)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=WORKSHEET_NAME, rows=1000, cols=50)

    # --- LIMPIEZA DE TEXTO ---
    def clean_line(line: str) -> str:
        line = re.sub(r'^[^\wÁÉÍÓÚÜÑáéíóúüñ]+', '', line.strip())
        if ":" in line:
            line = line.split(":", 1)[1].strip()
        return line

    valores = [clean_line(l) for l in texto.splitlines() if l.strip()]

    # --- ESCRITURA ---
    ws.append_row(valores, value_input_option="USER_ENTERED")

casas_avisar = {"williamhill", "betfair_ex_eu", "winamax_fr", "sport888"}

def normalizar_cuotas(cuotas:dict) -> dict:
    sum_probabilidades = sum(1/c for c in cuotas.values())
    if sum_probabilidades <= 1.15 and sum_probabilidades > 1:
        cuotas_normalizadas = {k:v*sum_probabilidades for k,v in cuotas.items()}
        return cuotas_normalizadas
    else:
        return cuotas

sent_messages = set()

def run_once():
    apikey='YOUR_API_KEY'

    sport='upcoming'
    url=f'https://api.the-odds-api.com/v4/sports/{sport}/odds'
    params = {'sport':'upcoming','apiKey':apikey, 'regions':'eu', 'markets':'h2h,spreads,totals'}

    response = requests.get(url, params=params).json()

    
    bot_token = 'TOKEN_BOT_TELEGRAM'
    url_telegram = f'https://api.telegram.org/bot{bot_token}/sendMessage'
    chat_id = 'CHAT_ID_TELEGRAM'

    
    now_utc=datetime.now(timezone.utc)
    upcoming=[]
    live=[]

    for game in response:
        if datetime.fromisoformat(game['commence_time'].replace('Z', '+00:00')) > now_utc:
            upcoming.append(game)
        else:
            live.append(game)
    
    guardar_data = {'response.json':response, 'upcoming.json':upcoming, 'live.json':live}
    for name, value in guardar_data.items():
        with open(name, 'w') as f:
            json.dump(value, f, indent=2)

    #Recolecta la informacion con formato {'idpartido':{'tipoapuesta':{
    #{'idpartido':
    #   {'tipoapuesta':{
    #       'casa':{
    #           'equipo':cuota,
    #           'otroequipo': cuota}
    #   ....
    #}
    recollection_upcoming = {}
    for game in upcoming:
        game_id=game['id']
        recollection_upcoming.update({game_id:{'h2h':{}, 'spreads':{}, 'totals':{}}})
        for bookmaker in game['bookmakers']:
            casa=bookmaker['key']
            for market in bookmaker['markets']:
                mode=market['key']
                for outcome in market['outcomes']:
                    if mode=='h2h':
                        recollection_upcoming[game_id][mode].setdefault(casa, {})[outcome['name']]=outcome['price']
                    elif mode=='spreads':
                        recollection_upcoming[game_id][mode].setdefault(casa, {})[outcome['name']+' '+str(outcome['point'])]=outcome['price']
                    elif mode=='totals':
                        recollection_upcoming[game_id][mode].setdefault(casa, {})[outcome['name']+' '+str(outcome['point'])]=outcome['price']
    recollection_live={}
    for game in live:
        game_id=game['id']
        recollection_live.update({game_id:{'h2h':{}, 'spreads':{}, 'totals':{}}})
        for bookmaker in game['bookmakers']:
            casa=bookmaker['key']
            for market in bookmaker['markets']:
                mode=market['key']
                for outcome in market['outcomes']:
                    if mode=='h2h':
                        recollection_live[game_id][mode].setdefault(casa, {})[outcome['name']]=outcome['price']
                    elif mode=='spreads':
                        recollection_live[game_id][mode].setdefault(casa, {})[outcome['name']+' '+str(outcome['point'])]=outcome['price']
                    elif mode=='totals':
                        recollection_live[game_id][mode].setdefault(casa, {})[outcome['name']+' '+str(outcome['point'])]=outcome['price']

    #Matematica
    for game in recollection_upcoming:
        ### H2H
        grouped_h2h_2outcomes={}
        grouped_h2h_3outcomes={}
        for casa, apuestas in recollection_upcoming[game]['h2h'].items():
            apuestas_normalizadas = normalizar_cuotas(apuestas)
            if len(apuestas) == 2:
                for bet_type, price in apuestas_normalizadas.items():
                    if bet_type not in grouped_h2h_2outcomes:
                        grouped_h2h_2outcomes[bet_type]={}
                    grouped_h2h_2outcomes[bet_type][casa]={'norm':price, 'raw':apuestas[bet_type]}
            elif len(apuestas) == 3:
                for bet_type, price in apuestas_normalizadas.items():
                    if bet_type not in grouped_h2h_3outcomes:
                        grouped_h2h_3outcomes[bet_type]={}
                    grouped_h2h_3outcomes[bet_type][casa]={'norm':price, 'raw':apuestas[bet_type]}
            else:
                print(f"h2h con outcome != 2 o !=3. Partido: {game} en casa {casa}. Apuestas: {apuestas}")
        
        for apuesta, casa_cuota in grouped_h2h_2outcomes.items():
            cuotas=list(d['norm'] for d in casa_cuota.values())
            mediana = median(cuotas)
            for casa, cuota in casa_cuota.items():
                if cuota['norm']/mediana >= 1.15 and mediana <= 4:
                    for juego in response:
                        if juego['id']==game:
                            nombre_partido = f"{juego['home_team']} vs {juego['away_team']}"
                            deporte = juego['sport_key']
                    message = f"🎯Valuebet detectada:\n🔜próximamente\n🏠Casa: {casa}\n🎫Tipo de apuesta: h2h_2outcomes\n🏅Apuesta: {apuesta}\n💰Cuota: {cuota['raw']}\n🗣️Partido: {nombre_partido}\n🏃‍➡️Deporte: {deporte}\n🕹️ID: {game}\n"
                    if message not in sent_messages:
                        print(message)
                        if casa in casas_avisar:
                            requests.get(url_telegram, params={'chat_id': chat_id, 'text':message})
                            sent_messages.add(message)
                            guardar_gsheets(message)
                    else:
                        print('Message already sent')
                    
        
        for apuesta, casa_cuota in grouped_h2h_3outcomes.items():
            cuotas=list(d['norm'] for d in casa_cuota.values())
            mediana = median(cuotas)
            for casa, cuota in casa_cuota.items():
                if cuota['norm']/mediana >= 1.15 and mediana <= 4:
                    for juego in response:
                        if juego['id']==game:
                            nombre_partido = f"{juego['home_team']} vs {juego['away_team']}"
                            deporte = juego['sport_key']
                    message = f"🎯Valuebet detectada:\n🔜próximamente\n🏠Casa: {casa}\n🎫Tipo de apuesta: h2h_3outcomes\n🏅Apuesta: {apuesta}\n💰Cuota: {cuota['raw']}\n🗣️Partido: {nombre_partido}\n🏃‍➡️Deporte: {deporte}\n🕹️ID: {game}\n"
                    if message not in sent_messages:
                        print(message)
                        if casa in casas_avisar:
                            requests.get(url_telegram, params={'chat_id': chat_id, 'text':message})
                            sent_messages.add(message)
                            guardar_gsheets(message)
                    else:
                        print('Message already sent')
        ### SPREADS
        grouped_spreads={}
        for casa, apuestas in recollection_upcoming[game]['spreads'].items():
            apuestas_normalizadas = normalizar_cuotas(apuestas)
            for bet_type, price in apuestas_normalizadas.items():
                if bet_type not in grouped_spreads:
                    grouped_spreads[bet_type]={}
                grouped_spreads[bet_type][casa]={'norm':price, 'raw':apuestas[bet_type]}

        for apuesta, casa_cuota in grouped_spreads.items():
            cuotas_norm=list(d['norm'] for d in casa_cuota.values())
            mediana = median(cuotas_norm)
            for casa, cuota in casa_cuota.items():
                if cuota['norm']/mediana >= 1.15 and mediana <= 4:
                    for juego in response:
                        if juego['id']==game:
                            nombre_partido = f"{juego['home_team']} vs {juego['away_team']}"
                            deporte = juego['sport_key']
                    message = f"🎯Valuebet detectada:\n🔜próximamente\n🏠Casa: {casa}\n🎫Tipo de apuesta: Spread\n🏅Apuesta: {apuesta}\n💰Cuota: {cuota['raw']}\n🗣️Partido: {nombre_partido}\n🏃‍➡️Deporte: {deporte}\n🕹️ID: {game}\n"
                    if message not in sent_messages:
                        print(message)
                        if casa in casas_avisar:
                            requests.get(url_telegram, params={'chat_id': chat_id, 'text':message})
                            sent_messages.add(message)
                            guardar_gsheets(message)
                    else:
                        print('Message already sent')
        ### TOTALS
        grouped_totals={}
        for casa, apuestas in recollection_upcoming[game]['totals'].items():
            apuestas_normalizadas = normalizar_cuotas(apuestas)
            for bet_type, price in apuestas_normalizadas.items():
                if bet_type not in grouped_totals:
                    grouped_totals[bet_type]={}
                grouped_totals[bet_type][casa]={'norm':price, 'raw':apuestas[bet_type]}

        for apuesta, casa_cuota in grouped_totals.items():
            cuotas=list(d['norm'] for d in casa_cuota.values())
            mediana = median(cuotas)
            for casa, cuota in casa_cuota.items():
                if cuota['norm']/mediana >= 1.15 and mediana <= 4:
                    for juego in response:
                        if juego['id']==game:
                            nombre_partido = f"{juego['home_team']} vs {juego['away_team']}"
                            deporte = juego['sport_key']
                    message = f"🎯Valuebet detectada:\n🔜próximamente\n🏠Casa: {casa}\n🎫Tipo de apuesta: Total\n🏅Apuesta: {apuesta}\n💰Cuota: {cuota['raw']}\n🗣️Partido: {nombre_partido}\n🏃‍➡️Deporte: {deporte}\n🕹️ID: {game}\n"
                    if message not in sent_messages:
                        print(message)
                        if casa in casas_avisar:
                            requests.get(url_telegram, params={'chat_id': chat_id, 'text':message})
                            sent_messages.add(message)
                            guardar_gsheets(message)
                    else:
                        print('Message already sent')
    
    for game in recollection_live:
            ### H2H
            grouped_h2h_2outcomes={}
            grouped_h2h_3outcomes={}
            for casa, apuestas in recollection_live[game]['h2h'].items():
                apuestas_normalizadas = normalizar_cuotas(apuestas)
                if len(apuestas) == 2:
                    for bet_type, price in apuestas_normalizadas.items():
                        if bet_type not in grouped_h2h_2outcomes:
                            grouped_h2h_2outcomes[bet_type]={}
                        grouped_h2h_2outcomes[bet_type][casa]={'norm':price, 'raw':apuestas[bet_type]}
                elif len(apuestas) == 3:
                    for bet_type, price in apuestas_normalizadas.items():
                        if bet_type not in grouped_h2h_3outcomes:
                            grouped_h2h_3outcomes[bet_type]={}
                        grouped_h2h_3outcomes[bet_type][casa]={'norm':price, 'raw':apuestas[bet_type]}
                else:
                    print(f"h2h con outcome != 2 o !=3. Partido: {game} en casa {casa}. Apuestas: {apuestas}")
            
            for apuesta, casa_cuota in grouped_h2h_2outcomes.items():
                cuotas=list(d['norm'] for d in casa_cuota.values())
                mediana = median(cuotas)
                for casa, cuota in casa_cuota.items():
                    if cuota['norm']/mediana >= 1.2 and mediana <= 4:
                        for juego in response:
                            if juego['id']==game:
                                nombre_partido = f"{juego['home_team']} vs {juego['away_team']}"
                                deporte = juego['sport_key']
                        message = f"🎯Valuebet detectada:\n🔴directo\n🏠Casa: {casa}\n🎫Tipo de apuesta: h2h_2outcomes\n🏅Apuesta: {apuesta}\n💰Cuota: {cuota['raw']}\n🗣️Partido: {nombre_partido}\n🏃‍➡️Deporte: {deporte}\n🕹️ID: {game}\n"
                        print(message)
                        #if casa in casas_avisar:
                        #    requests.get(url_telegram, params={'chat_id': chat_id, 'text':message})
                        
            
            for apuesta, casa_cuota in grouped_h2h_3outcomes.items():
                cuotas=list(d['norm'] for d in casa_cuota.values())
                mediana = median(cuotas)
                for casa, cuota in casa_cuota.items():
                    if cuota['norm']/mediana >= 1.2 and mediana <= 4:
                        for juego in response:
                            if juego['id']==game:
                                nombre_partido = f"{juego['home_team']} vs {juego['away_team']}"
                                deporte = juego['sport_key']
                        message = f"🎯Valuebet detectada:\n🔴directo\n🏠Casa: {casa}\n🎫Tipo de apuesta: h2h_3outcomes\n🏅Apuesta: {apuesta}\n💰Cuota: {cuota['raw']}\n🗣️Partido: {nombre_partido}\n🏃‍➡️Deporte: {deporte}\n🕹️ID: {game}\n"
                        print(message)
                        #if casa in casas_avisar:
                        #    requests.get(url_telegram, params={'chat_id': chat_id, 'text':message})
            ### SPREADS
            grouped_spreads={}
            for casa, apuestas in recollection_live[game]['spreads'].items():
                apuestas_normalizadas = normalizar_cuotas(apuestas)
                for bet_type, price in apuestas_normalizadas.items():
                    if bet_type not in grouped_spreads:
                        grouped_spreads[bet_type]={}
                    grouped_spreads[bet_type][casa]={'norm':price, 'raw':apuestas[bet_type]}

            for apuesta, casa_cuota in grouped_spreads.items():
                cuotas_norm=list(d['norm'] for d in casa_cuota.values())
                mediana = median(cuotas_norm)
                for casa, cuota in casa_cuota.items():
                    if cuota['norm']/mediana >= 1.2 and mediana <= 4:
                        for juego in response:
                            if juego['id']==game:
                                nombre_partido = f"{juego['home_team']} vs {juego['away_team']}"
                                deporte = juego['sport_key']
                        message = f"🎯Valuebet detectada:\n🔴directo\n🏠Casa: {casa}\n🎫Tipo de apuesta: Spread\n🏅Apuesta: {apuesta}\n💰Cuota: {cuota['raw']}\n🗣️Partido: {nombre_partido}\n🏃‍➡️Deporte: {deporte}\n🕹️ID: {game}\n"
                        print(message)
                        #if casa in casas_avisar:
                        #    requests.get(url_telegram, params={'chat_id': chat_id, 'text':message})
            ### TOTALS
            grouped_totals={}
            for casa, apuestas in recollection_live[game]['totals'].items():
                apuestas_normalizadas = normalizar_cuotas(apuestas)
                for bet_type, price in apuestas_normalizadas.items():
                    if bet_type not in grouped_totals:
                        grouped_totals[bet_type]={}
                    grouped_totals[bet_type][casa]={'norm':price, 'raw':apuestas[bet_type]}

            for apuesta, casa_cuota in grouped_totals.items():
                cuotas=list(d['norm'] for d in casa_cuota.values())
                mediana = median(cuotas)
                for casa, cuota in casa_cuota.items():
                    if cuota['norm']/mediana >= 1.2 and mediana <= 4:
                        for juego in response:
                            if juego['id']==game:
                                nombre_partido = f"{juego['home_team']} vs {juego['away_team']}"
                                deporte = juego['sport_key']
                        message = f"🎯Valuebet detectada:\n🔴directo\n🏠Casa: {casa}\n🎫Tipo de apuesta: Total\n🏅Apuesta: {apuesta}\n💰Cuota: {cuota['raw']}\n🗣️Partido: {nombre_partido}\n🏃‍➡️Deporte: {deporte}\n🕹️ID: {game}\n"
                        print(message)
                        #if casa in casas_avisar:
                        #    requests.get(url_telegram, params={'chat_id': chat_id, 'text':message})

    with open('recollection_upcoming.json', 'w') as f:
        json.dump(recollection_upcoming, f, indent=2)
    with open('recollection_live.json', 'w') as f:
        json.dump(recollection_live, f, indent=2)

def job():
    try:
        run_once()
    except Exception as e:
        print('Error en run_once', e)

if __name__ == '__main__':        
    job()
    schedule.every(5).minutes.do(job)
    try:
        while True:
            schedule.run_pending()
            time.sleep(10)
    except KeyboardInterrupt:
        print('Detección finalizada.')
