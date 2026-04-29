import streamlit as st
import pandas as pd
import re
from io import BytesIO



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
    

if df_agend is not None and df_evol is not None:
    
    df_agend['PROFISSIONAL'] = df_agend['PROFISSIONAL'].str.split('(').str[0].str.strip()
    df_agend['PROFISSIONAL'] = df_agend['PROFISSIONAL'].str.split('-').str[0].str.strip()

    df_evol['PROFISSIONAL'] = df_evol['PROFISSIONAL'].str.split('(').str[0].str.strip()
        
    df_profissionais = pd.read_excel("funcionarios_setor.xlsx")


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
    
    