import os
import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# Pegamos a URL de conexão direto da nuvem
DATABASE_URL = os.getenv("DATABASE_URL")

def get_connection():
    try:
        return psycopg2.connect(DATABASE_URL)
    except Exception as err:
        print(f"Erro ao conectar ao banco: {err}")
        raise HTTPException(status_code=500, detail="Erro de conexão com o banco de dados")

# FUNÇÃO CRUCIAL: Cria a tabela automaticamente se ela não existir na nuvem
def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS consultas (
            id SERIAL PRIMARY KEY,
            ip VARCHAR(45) NOT NULL,
            tp_cliente VARCHAR(10) NOT NULL,
            valor DECIMAL(10,2) NOT NULL,
            cashback DECIMAL(10,2) NOT NULL,
            dt_insert TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        conn.commit()
    except Exception as e:
        print(f"Erro ao inicializar tabela: {e}")
    finally:
        cursor.close()
        conn.close()

# Inicializa o banco assim que o app liga
init_db()

def calcular_cashback(valor_produto, percentual_desconto, vip):
    valor_final_compra = valor_produto * (1 - percentual_desconto / 100)
    cashback_base = valor_final_compra * 0.05
    
    if vip:
        bonus_vip = cashback_base * 0.10
        cashback_total = cashback_base + bonus_vip
    else:
        cashback_total = cashback_base        
        
    if valor_produto > 500:
        cashback_final = cashback_total * 2
    else:
        cashback_final = cashback_total
        
    return round(cashback_final, 2)


@app.get("/cashback")
def get_cashback(request: Request, valor: float, desconto: float = 0, vip: bool = False):
    ip = request.client.host
    cashback = calcular_cashback(valor, desconto, vip)
    tp_cliente = "VIP" if vip else "NORMAL"
    valor_final = valor - (valor * (desconto / 100))

    conn = get_connection()
    cursor = conn.cursor()

    try:
        # No PostgreSQL usa-se %s para os parâmetros
        query = """
        INSERT INTO consultas (ip, tp_cliente, valor, cashback)
        VALUES (%s, %s, %s, %s) 
        """
        cursor.execute(query, (ip, tp_cliente, valor_final, cashback))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erro ao salvar no banco: {e}")
    finally:
        cursor.close()
        conn.close()

    return {
        "ip": ip,
        "valor_original": valor,
        "valor_com_desconto": round(valor_final, 2),
        "desconto_percentual": desconto,
        "vip": vip,
        "cashback": cashback
    }


@app.get("/historico")
def get_historico(request: Request):
    ip = request.client.host
    
    conn = get_connection()
    # RealDictCursor faz o Postgres retornar os dados como dicionário/JSON (igual ao dictionary=True do MySQL)
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    try:
        query = """
        SELECT ip, tp_cliente, valor, cashback, dt_insert 
        FROM consultas 
        WHERE ip = %s
        ORDER BY dt_insert DESC
        """
        cursor.execute(query, (ip,))
        resultado_consulta = cursor.fetchall()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao buscar histórico: {e}")
    finally:
        cursor.close()
        conn.close()

    for row in resultado_consulta:
        if "dt_insert" in row and row["dt_insert"]:
            row["dt_insert"] = row["dt_insert"].strftime("%Y-%m-%d %H:%M:%S")

    return {
        "ip": ip,
        "historico": resultado_consulta
    }