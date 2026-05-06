import streamlit as st
import pandas as pd
import re
from io import BytesIO
import mysql.connector
import math
import time

conn = mysql.connector.connect(
    host="mysql20-farm1.kinghost.net",
    user="afr0202_add1",
    password="La12345",
    database="afr02", 
    port=3306
)

mycursor = conn.cursor()
def limpar(val):
    if val is None:
        return None
    if isinstance(val, float) and math.isnan(val):
        return None
    try:
        if math.isnan(float(val)):
            return None
    except (TypeError, ValueError):
        pass
    return val

def df_to_mysql(df: pd.DataFrame, table: str, conn):
    cursor = conn.cursor()

    # Verifica se a tabela existe
    cursor.execute("""
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_schema = DATABASE()
        AND table_name = %s
    """, (table,))

    existe = cursor.fetchone()[0] > 0

    if not existe:
        tipo_map = {
            "int64":   "BIGINT",
            "int32":   "INT",
            "float64": "DOUBLE",
            "float32": "FLOAT",
            "bool":    "TINYINT(1)",
            "object":  "TEXT",
        }
        colunas = ", ".join(
            f"`{col}` {tipo_map.get(str(df[col].dtype), 'TEXT')}"
            for col in df.columns
        )
        cursor.execute(f"CREATE TABLE `{table}` ({colunas})")
        conn.commit()
        print(f"[OK] Tabela '{table}' criada.")

    placeholders = ", ".join(["%s"] * len(df.columns))
    colunas_str  = ", ".join(f"`{c}`" for c in df.columns)
    sql = f"INSERT INTO `{table}` ({colunas_str}) VALUES ({placeholders})"

    # iterrows garante que cada célula passa pela limpeza
    rows = [
        tuple(limpar(val) for val in row)
        for _, row in df.iterrows()
    ]

    cursor.executemany(sql, rows)
    conn.commit()

    print(f"[OK] {len(df)} linhas gravadas em '{table}' (modo: {'append' if existe else 'create'})")
    cursor.close()

# Função para limpar o nome do profissional (trata NaN)
def limpar_profissional(nome):
    if pd.isna(nome):
        return None
    nome = str(nome)
    nome = re.sub(r'\s*-\s*[^(]+(?=\()', '', nome)  # remove " - PILATES 1" etc.
    return nome.strip()

st.title("Relatório de Agendamento e Evoluções")

file1 = st.file_uploader("Adicione o arquivo de agendamento")
file2 = st.file_uploader("Adicione o arquivo de evoluções")

df_agend = None
df_evol = None

if file1 and file2:
    df_agend = pd.read_excel(file1, skipfooter=1)
    df_evol = pd.read_excel(file2, skipfooter=1)

    st.write("Arquivo de Agendamento:")
    st.dataframe(df_agend)

    st.write("Arquivo de Evoluções:")
    st.dataframe(df_evol)
    

tab1, tab2 = st.tabs(["Evoluções e Agendamentos", "Funcionários da AFR"])

with tab1:
    if df_agend is not None and df_evol is not None:
        
        df_agend['PROFISSIONAL'] = df_agend['PROFISSIONAL'].str.split('(').str[0].str.strip()
        df_agend['PROFISSIONAL'] = df_agend['PROFISSIONAL'].str.split('-').str[0].str.strip()

        df_evol['PROFISSIONAL'] = df_evol['PROFISSIONAL'].str.split('(').str[0].str.strip()
            
        df_profissionais = pd.read_sql(
            "SELECT `Nome do Funcionário`, `Setor` FROM funcionarios_setor", conn
        )


        # Criar coluna auxiliar com nome limpo
        df_agend['PROF_LIMPO'] = df_agend['PROFISSIONAL'].apply(limpar_profissional)
        df_evol['PROF_LIMPO']  = df_evol['PROFISSIONAL'].apply(limpar_profissional)

        # Garantir que DATA está no mesmo formato nos dois
        df_agend = df_agend[pd.to_datetime(df_agend['DATA'], dayfirst=True, errors='coerce').notna()].copy()
        df_evol  = df_evol[pd.to_datetime(df_evol['DATA'],   dayfirst=True, errors='coerce').notna()].copy()

        # Agrupar agendamentos: pacientes únicos por PROF_LIMPO + DATA
        df_pacientes = (
            df_agend
            .dropna(subset=['PROF_LIMPO'])
            .groupby(['PROF_LIMPO', 'DATA'])['ATENDIDO']
            .nunique()
            .reset_index()
            .rename(columns={'ATENDIDO': 'Nº DE PACIENTES'})
        )

        # Agrupar evoluções: contagem de linhas por PROF_LIMPO + DATA
        df_evolucoes = (
            df_evol
            .dropna(subset=['PROF_LIMPO'])
            .groupby(['PROF_LIMPO', 'DATA'])['ATENDIDO']
            .count()
            .reset_index()
            .rename(columns={'ATENDIDO': 'Nº DE EVOLUÇÕES'})
        )

        # Merge pelos campos limpos
        df_resultado = df_pacientes.merge(df_evolucoes, on=['PROF_LIMPO', 'DATA'], how='left')

        # Recuperar o nome original do profissional (do df_agend)
        nomes_originais = (
            df_agend[['PROF_LIMPO', 'PROFISSIONAL']]
            .dropna(subset=['PROF_LIMPO'])
            .drop_duplicates('PROF_LIMPO')
        )

        df_resultado = df_resultado.merge(nomes_originais, on='PROF_LIMPO', how='left')

        # Montar dataframe final com colunas desejadas
        df_final = (
            df_resultado[['PROFISSIONAL', 'DATA', 'Nº DE PACIENTES', 'Nº DE EVOLUÇÕES']]
            .sort_values(['PROFISSIONAL', 'DATA'])
            .reset_index(drop=True)
        )

        # Preencher evoluções sem correspondência com 0
        df_final['Nº DE EVOLUÇÕES'] = df_final['Nº DE EVOLUÇÕES'].fillna(0).astype(int)
        
        df_final['PROFISSIONAL'] = df_final['PROFISSIONAL'].str.split('(').str[0].str.strip()
        df_final = df_final.merge(df_profissionais, left_on='PROFISSIONAL', right_on="Nome do Funcionário", how='left')
        df_final = df_final[['PROFISSIONAL', 'DATA', "Nº DE PACIENTES", "Nº DE EVOLUÇÕES", "Setor"]]
        df_final.columns = df_final.columns.str.upper()


        st.write("Relatório Final:")
        st.dataframe(df_final)
        
        buffer = BytesIO()
        df_final.to_excel(buffer, index=False, engine='openpyxl')
        buffer.seek(0)

        st.download_button(
            label="Download do Relatório Final",
            data=buffer,
            file_name="relatorio_final.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        
        if st.button("Enviar para MySQL", key="enviar_mysql_final"):
            df_to_mysql(df_final, "relatorio_agendamento_evolucoes", conn)
            st.success("Dados enviados para MySQL com sucesso!")

        st.write("Planilhas do Reintegrar:")
        
        df_pacientes_reint = df_pacientes.merge(df_profissionais, left_on='PROF_LIMPO', right_on="Nome do Funcionário", how='left').rename(columns={'PROF_LIMPO': 'PROFISSIONAL', 'Setor': 'SETOR'})[['PROFISSIONAL', 'Nº DE PACIENTES', 'DATA', 'SETOR']]
        df_pacientes_reint = df_pacientes_reint[df_pacientes_reint['SETOR'] == 'Reintegrar']

        st.dataframe(df_pacientes_reint)
        
        buffer2 = BytesIO()
        df_pacientes_reint.to_excel(buffer2, index=False, engine='openpyxl')
        buffer2.seek(0)

        st.download_button(
            label="Download Agendamentos Reintegrar",
            data=buffer2,
            file_name="agendamentos_reintegar.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        
        if st.button("Enviar para o MySQL", key="enviar_mysql_reint"):
            df_to_mysql(df_pacientes_reint, "agendamentos_reintegrar", conn)
            st.success("Dados de agendamento do Reintegrar enviados para MySQL com sucesso!")

        df_evolucoes_reint = df_evolucoes.merge(df_profissionais, left_on='PROF_LIMPO', right_on="Nome do Funcionário", how='left').rename(columns={'PROF_LIMPO': 'PROFISSIONAL', 'Setor': 'SETOR'})[['PROFISSIONAL', 'Nº DE EVOLUÇÕES', 'DATA', 'SETOR']]
        df_evolucoes_reint = df_evolucoes_reint[df_evolucoes_reint['SETOR'] == 'Reintegrar']
        st.dataframe(df_evolucoes_reint)
        
        buffer3 = BytesIO()
        df_evolucoes_reint.to_excel(buffer3, index=False, engine='openpyxl')
        buffer3.seek(0)
        
        st.download_button(
            label="Download Evoluções Reintegrar",
            data=buffer3,
            file_name="evolucoes_reintegar.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        if st.button("Enviar para o MySQL", key="enviar_mysql_evol_reint"):
            df_to_mysql(df_evolucoes_reint, "evolucoes_reintegrar", conn)
            st.success("Dados de evoluções do Reintegrar enviados para MySQL com sucesso!")
        
with tab2:
    st.markdown("## Funcionários da AFR:")
    
    df_funcionarios_afr = pd.read_sql(
        "SELECT `id`, `Nome do Funcionário`, `Setor` FROM funcionarios_setor", conn
    )
    df_funcionarios_afr['Selecionar'] = False  # coluna para checkbox de seleção
    
    edited_funcionarios_afr = st.data_editor(
        df_funcionarios_afr,
        num_rows="dynamic",
        use_container_width=True,
        disabled=["id"],  # impede o usuário de editar o id
    )
    
    funcionario_input = st.text_input("Adicionar novo funcionário:")
    setor_input = st.text_input("Setor do novo funcionário:")
    
    if st.button("Adicionar Funcionário AFR"):
        if funcionario_input and setor_input:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO funcionarios_setor (`Nome do Funcionário`, `Setor`)
                VALUES (%s, %s)
            """, (funcionario_input, setor_input))
            conn.commit()
            cursor.close()
            st.success(f"Funcionário '{funcionario_input}' adicionado com sucesso!")
            st.rerun()  # recarrega a página para mostrar o novo funcionário
        else:
            st.warning("Por favor, preencha ambos os campos para adicionar um funcionário.")

    if st.button("Editar Funcionários AFR"):
        cursor = conn.cursor()
        for _, row in edited_funcionarios_afr.iterrows():
            if pd.isna(row['id']):
                # Linha nova adicionada no data_editor — faz INSERT
                cursor.execute("""
                    INSERT INTO funcionarios_setor (`Nome do Funcionário`, `Setor`)
                    VALUES (%s, %s)
                """, (row['Nome do Funcionário'], row['Setor']))
            else:
                # Linha existente — faz UPDATE pela chave
                cursor.execute("""
                    UPDATE funcionarios_setor
                    SET `Nome do Funcionário` = %s,
                        `Setor` = %s
                    WHERE `id` = %s
                """, (row['Nome do Funcionário'], row['Setor'], int(row['id'])))
        conn.commit()
        cursor.close()
        st.success("Funcionários da AFR atualizados com sucesso!")
        st.rerun()  # recarrega a página para mostrar as atualizações
        
        # botão para apagar
    if st.button("🗑️ Apagar registros de funcionários"):
        selecionados = edited_funcionarios_afr[edited_funcionarios_afr["Selecionar"]]

        if not selecionados.empty:
            ids = selecionados["id"].tolist()
            try:
                cursor = conn.cursor()
                cursor.executemany(
                    "DELETE FROM funcionarios_setor WHERE id = %s",
                    [(int(id_reg),) for id_reg in ids]
                )
                conn.commit()
                st.success(f"{len(ids)} registro(s) apagado(s).")
                st.rerun()  # ← fix #5
            except Exception as e:
                conn.rollback()
                st.error(f"Erro ao apagar registros: {e}")
            finally:
                cursor.close()
        else:
            st.warning("Nenhum funcionário selecionado.")
