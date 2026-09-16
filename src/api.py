import requests
import logging
from typing import Dict, List, Any, Optional
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DadosAbertosPBAPI:
    """
    Cliente para a API Dados Abertos PB.
    
    Fornece acesso aos dados públicos da Paraíba em categorias como:
    - Servidores e remuneração
    - Despesas e notas de empenho
    - Compras, contratações e contratos
    """

    def __init__(self, base_url: str = "https://api.dadosabertos.codata.pb.gov.br/api/v1", 
                 timeout: int = 30, max_retries: int = 3):
        """
        Inicializa o cliente da API.
        
        Args:
            base_url: URL base da API
            timeout: Tempo limite para requisições (segundos)
            max_retries: Número máximo de tentativas para requisições
        """
        self.base_url = base_url
        self.timeout = timeout
        self.session = self._criar_sessao_com_retry(max_retries)

    def _criar_sessao_com_retry(self, max_retries: int) -> requests.Session:
        """
        Cria uma sessão com estratégia de retry automático.
        
        Args:
            max_retries: Número máximo de tentativas
            
        Returns:
            Session configurada com retry strategy
        """
        sessao = requests.Session()
        sessao.headers.update({"Accept": "application/json"})
        
        # Configurar retry strategy para conexões falhas
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"]
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        sessao.mount("http://", adapter)
        sessao.mount("https://", adapter)
        
        return sessao

    def _get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Realiza uma requisição GET à API.
        
        Args:
            endpoint: Caminho do endpoint (sem base_url)
            params: Parâmetros da query
            
        Returns:
            Response JSON da API
            
        Raises:
            requests.RequestException: Em caso de erro na requisição
        """
        url = f"{self.base_url}/{endpoint}"
        
        try:
            logger.debug(f"GET {url} com params: {params}")
            response = self.session.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        
        except requests.exceptions.Timeout:
            logger.error(f"Timeout ao acessar {url}")
            raise
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Erro de conexão ao acessar {url}: {e}")
            raise
        except requests.exceptions.HTTPError as e:
            logger.error(f"Erro HTTP {response.status_code} ao acessar {url}: {response.text}")
            raise
        except ValueError as e:
            logger.error(f"Erro ao decodificar JSON de {url}: {e}")
            raise

    def _listar_paginado(
        self,
        endpoint: str,
        ano: Optional[int] = None,
        mes: Optional[int] = None,
        pagina: int = 1,
        parametros_extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Método genérico para listar dados com paginação.

        Os endpoints não usam sempre os mesmos parâmetros. Em alguns casos, o filtro
        relevante é "ano" e "mes"; em outros, o campo é "anoInicioVigencia".
        """
        params: Dict[str, Any] = {"page": pagina}

        if parametros_extra:
            params.update(parametros_extra)

        if ano is not None:
            params["ano"] = ano
        if mes is not None:
            params["mes"] = str(mes).zfill(2)

        return self._get(endpoint, params)

    def _obter_todos_registros(
        self,
        endpoint: str,
        ano: Optional[int] = None,
        mes: Optional[int] = None,
        parametros_extra: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Obtém todos os registros de um endpoint paginado.
        """
        pagina = 1
        todos_registros = []

        while True:
            try:
                resposta = self._listar_paginado(
                    endpoint,
                    ano=ano,
                    mes=mes,
                    pagina=pagina,
                    parametros_extra=parametros_extra,
                )

                registros = resposta.get("dados", [])
                paginacao = resposta.get("paginacao", {})

                todos_registros.extend(registros)

                total_paginas = paginacao.get("total_paginas", 1)
                logger.info(
                    f"Página {pagina}/{total_paginas} - "
                    f"Total acumulado: {len(todos_registros)} registros"
                )

                if pagina >= total_paginas:
                    break

                pagina += 1

            except requests.RequestException as e:
                logger.error(f"Erro ao buscar página {pagina}: {e}")
                raise

        return todos_registros

    # ==================== ENDPOINTS DE SERVIDORES ====================
    
    def listar_servidores(self, ano: int = 2026, mes: int = 1, pagina: int = 1) -> Dict[str, Any]:
        """
        Lista servidores públicos com dados de remuneração.
        
        Args:
            ano: Ano do exercício
            mes: Mês
            pagina: Número da página
            
        Returns:
            Dados de servidores paginados
        """
        return self._listar_paginado("remuneracao/servidor", ano, mes, pagina)

    def obter_todos_servidores(self, ano: int = 2026, mes: int = 1) -> List[Dict[str, Any]]:
        """Obtém todos os servidores (todas as páginas)."""
        return self._obter_todos_registros("remuneracao/servidor", ano, mes)

    # ==================== ENDPOINTS DE DESPESAS ====================
    
    def listar_notas_empenho(self, ano: int = 2026, mes: int = 5, pagina: int = 1) -> Dict[str, Any]:
        """
        Lista notas de empenho (comprometimento de despesa).
        
        Args:
            ano: Ano do exercício
            mes: Mês
            pagina: Número da página
            
        Returns:
            Dados de notas de empenho paginados
        """
        return self._listar_paginado("despesas/notas_empenho", ano, mes, pagina)

    def obter_todas_notas_empenho(self, ano: int = 2026, mes: int = 5) -> List[Dict[str, Any]]:
        """Obtém todas as notas de empenho (todas as páginas)."""
        return self._obter_todos_registros("despesas/notas_empenho", ano, mes)

    def listar_liquidacoes(self, ano: int = 2026, mes: int = 5, pagina: int = 1) -> Dict[str, Any]:
        """
        Lista liquidações de despesas.
        
        Args:
            ano: Ano do exercício
            mes: Mês
            pagina: Número da página
            
        Returns:
            Dados de liquidações paginados
        """
        return self._listar_paginado("despesas/liquidacoes", ano, mes, pagina)

    def obter_todas_liquidacoes(self, ano: int = 2026, mes: int = 5) -> List[Dict[str, Any]]:
        """Obtém todas as liquidações (todas as páginas)."""
        return self._obter_todos_registros("despesas/liquidacoes", ano, mes)

    # ==================== ENDPOINTS DE COMPRAS ====================
    



    def listar_contratacoes(self, ano: int = 2026, mes: int = 5, pagina: int = 1) -> Dict[str, Any]:
        """
        Lista contratações/licitações.
        
        Args:
            ano: Ano do exercício
            mes: Mês
            pagina: Número da página
            
        Returns:
            Dados de contratações paginados
        """
        return self._listar_paginado("compras/contratacoes", ano, mes, pagina)

    def obter_todas_contratacoes(self, ano: int = 2026, mes: int = 5) -> List[Dict[str, Any]]:
        """Obtém todas as contratações (todas as páginas)."""
        return self._obter_todos_registros("compras/contratacoes", ano, mes)




    def listar_contratos(
        self,
        ano_inicio_vigencia: int,
        pagina: int = 1,
    ) -> Dict[str, Any]:
        """
        Lista contratos celebrados.

        Este endpoint exige o parâmetro anoInicioVigencia e não usa ano/mes.
        """
        params: Dict[str, Any] = {"page": pagina, "anoInicioVigencia": ano_inicio_vigencia}
        return self._get("compras/contratos", params)

    def obter_todos_contratos(self, ano_inicio_vigencia: int) -> List[Dict[str, Any]]:
        """Obtém todos os contratos (todas as páginas)."""
        pagina = 1
        todos_registros = []

        while True:
            resposta = self.listar_contratos(
                ano_inicio_vigencia=ano_inicio_vigencia,
                pagina=pagina,
            )

            registros = resposta.get("dados", [])
            paginacao = resposta.get("paginacao", {})
            todos_registros.extend(registros)

            total_paginas = paginacao.get("total_paginas", 1)
            if pagina >= total_paginas:
                break
            pagina += 1

        return todos_registros




    def listar_itens_contratacoes(self, ano: int = 2026, mes: int = 5, pagina: int = 1) -> Dict[str, Any]:
        """
        Lista itens de contratações.
        
        Args:
            ano: Ano do exercício
            mes: Mês
            pagina: Número da página
            
        Returns:
            Dados de itens paginados
        """
        return self._listar_paginado("compras/itens_contratacoes", ano, mes, pagina)

    def obter_todos_itens_contratacoes(self, ano: int = 2026, mes: int = 5) -> List[Dict[str, Any]]:
        """Obtém todos os itens de contratações (todas as páginas)."""
        return self._obter_todos_registros("compras/itens_contratacoes", ano, mes)




    def listar_ata_registro_preco(
        self,
        ano: Optional[int] = None,
        mes: Optional[int] = None,
        pagina: int = 1,
        ano_inicio_vigencia: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Lista atas de registro de preço.

        Validação real da API: este endpoint exige o parâmetro 'ano'.
        Mantemos um alias 'ano_inicio_vigencia' apenas para compatibilidade,
        mas o valor é repassado para 'ano' antes da requisição.
        """
        if ano is None and ano_inicio_vigencia is not None:
            ano = ano_inicio_vigencia

        params: Dict[str, Any] = {"page": pagina}
        if ano is not None:
            params["ano"] = ano
        if mes is not None:
            params["mes"] = str(mes).zfill(2)

        return self._get("compras/ata_registro_preco", params)

    def obter_todas_atas_registro_preco(
        self,
        ano: Optional[int] = None,
        mes: Optional[int] = None,
        ano_inicio_vigencia: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Obtém todas as atas de registro de preço (todas as páginas)."""
        if ano is None and ano_inicio_vigencia is not None:
            ano = ano_inicio_vigencia

        pagina = 1
        todos_registros = []

        while True:
            resposta = self.listar_ata_registro_preco(
                ano=ano,
                mes=mes,
                pagina=pagina,
            )

            registros = resposta.get("dados", [])
            paginacao = resposta.get("paginacao", {})
            todos_registros.extend(registros)

            total_paginas = paginacao.get("total_paginas", 1)
            if pagina >= total_paginas:
                break
            pagina += 1

        return todos_registros

