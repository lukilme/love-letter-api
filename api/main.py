import requests
import csv
import os
import json


class SEADParaibaCSV:

    def __init__(self):
        self.base_url = "https://api.dadosabertos.codata.pb.gov.br/api/v1/remuneracao"

        self.session = requests.Session()

        self.session.headers.update({"Accept": "application/json"})

    def buscar_pagina(self, ano, mes, pagina):
        """Busca uma página específica da API."""

        url = f"{self.base_url}/servidor"

        params = {"ano": str(ano), "mes": str(mes).zfill(2), "page": pagina}

        try:
            response = self.session.get(url, params=params, timeout=30)

            response.raise_for_status()

            return response.json()

        except requests.exceptions.RequestException as erro:
            print(f"Erro ao buscar página {pagina}: {erro}")
            return None

    def localizar_lista(self, dados_json):
        """
        Descobre dinamicamente onde está a lista
        de servidores dentro da resposta JSON.
        """

        if isinstance(dados_json, list):
            return dados_json

        if isinstance(dados_json, dict):

            chaves_comuns = ["data", "dados", "results", "items", "servidores"]

            for chave in chaves_comuns:

                if chave in dados_json:

                    if isinstance(dados_json[chave], list):
                        return dados_json[chave]

            for chave, valor in dados_json.items():

                if isinstance(valor, list):
                    return valor

        return []

    def buscar_todos_dados(self, ano, mes):
        """
        Busca automaticamente todas as páginas
        disponíveis na API.
        """

        todos_servidores = []

        pagina = 1

        while True:

            print(f"Baixando página {pagina}...")

            dados = self.buscar_pagina(ano, mes, pagina)

            if dados is None:
                print("Erro na requisição. Encerrando extração.")
                break

            lista_servidores = self.localizar_lista(dados)

            if not lista_servidores:

                print(
                    f"Nenhum registro encontrado na página "
                    f"{pagina}. Fim da paginação."
                )

                break

            print(
                f"Página {pagina}: " f"{len(lista_servidores)} registros encontrados."
            )

            todos_servidores.extend(lista_servidores)

            pagina += 1

        return todos_servidores

    def exportar_para_csv(self, ano, mes):

        nome_arquivo = f"servidores_pb_{ano}_{str(mes).zfill(2)}.csv"

        print("=" * 60)
        print("INICIANDO EXTRAÇÃO")
        print("=" * 60)

        servidores = self.buscar_todos_dados(ano, mes)

        if not servidores:

            print("Nenhum dado encontrado.")

            return

        print("\nDescobrindo todas as colunas...")

        cabecalhos = set()

        for servidor in servidores:

            cabecalhos.update(servidor.keys())

        cabecalhos = sorted(cabecalhos)

        print(f"Total de registros: {len(servidores)}")

        print(f"Total de colunas: {len(cabecalhos)}")

        print("\nSalvando CSV...")

        with open(
            nome_arquivo, mode="w", newline="", encoding="utf-8-sig"
        ) as arquivo_csv:

            escritor = csv.DictWriter(
                arquivo_csv, fieldnames=cabecalhos, delimiter=";", extrasaction="ignore"
            )

            escritor.writeheader()

            escritor.writerows(servidores)

        print("\n" + "=" * 60)

        print("EXTRAÇÃO CONCLUÍDA")

        print(f"Arquivo salvo em:\n" f"{os.path.abspath(nome_arquivo)}")

        print(f"\nTotal de servidores/registros: " f"{len(servidores)}")

        print("=" * 60)


if __name__ == "__main__":

    extrator = SEADParaibaCSV()

    extrator.exportar_para_csv(ano=2025, mes=10)
