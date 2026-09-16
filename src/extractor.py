from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from src.api import DadosAbertosPBAPI
import pandas as pd
from requests.exceptions import RequestException

logger = logging.getLogger(__name__)


class BaseExtractor(ABC):
    """Classe base para qualquer extrator que use períodos (ano/mês) e salve dados.

    Para criar um comportamento específico, basta herdar desta classe e implementar
    os métodos abstratos ou sobrescrever os pontos de extensão.
    """

    def __init__(self, api: DadosAbertosPBAPI, output_dir: str = "."):
        self.api : DadosAbertosPBAPI = api
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.stats: Dict[str, Any] = {
            "total_registros": 0,
            "anos_processados": [],
            "meses_processados": [],
            "erros": [],
        }

    @property
    @abstractmethod
    def resource_name(self) -> str:
        """Nome do recurso em uso, por exemplo: 'notas_empenho'."""

    @property
    def period_mode(self) -> str:
        """Define como o recurso é filtrado: 'ano_mes' ou 'ano_inicio_vigencia'."""
        return "ano_mes"

    def fetch_month_records(self, year: int, month: int) -> List[Dict[str, Any]]:
        """Implementa a extração de um mês específico.

        Compatibilidade: subclasses antigas podem implementar `fetch_all(year, month)`,
        enquanto subclasses novas podem implementar `fetch_month_records(year, month)`.
        """
        if type(self).fetch_all is not BaseExtractor.fetch_all:
            return self.fetch_all(year, month)

        raise NotImplementedError(
            f"{self.__class__.__name__} precisa implementar fetch_month_records(year, month) "
            "ou fetch_all(year, month)."
        )

    def fetch_all(self, year: int, month: int) -> List[Dict[str, Any]]:
        """Alias legado para manter compatibilidade com implementações anteriores."""
        return self.fetch_month_records(year, month)

    def unwrap_records(self, payload: Any) -> List[Dict[str, Any]]:
        """Normaliza retornos da API, que podem vir como lista ou como dict paginado."""
        if isinstance(payload, list):
            return payload

        if isinstance(payload, dict):
            if isinstance(payload.get("dados"), list):
                return payload["dados"]

            for value in payload.values():
                if isinstance(value, list):
                    return value

        return []

    def normalize_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Hook opcional para padronizar cada registro antes de salvar."""
        return record

    def validate_period(self, year: int, month: Optional[int] = None) -> bool:
        """Valida o período antes de executar a extração."""
        if year < 2000:
            logger.warning(f"Ano inválido: {year}")
            return False

        if month is not None and (month < 1 or month > 12):
            logger.warning(f"Mês inválido: {month}")
            return False

        return True

    def extract_month(self, year: int, month: int, verbose: bool = True) -> List[Dict[str, Any]]:
        """Extrai os registros de um mês específico."""
        if not self.validate_period(year, month):
            return []

        try:
            if verbose:
                logger.info(f"Extraindo {year}-{month:02d}...")

            raw_records = self.fetch_month_records(year, month)
            records = self.unwrap_records(raw_records)
            normalized = [self.normalize_record(item) for item in records]

            if verbose:
                logger.info(f"Extraído {year}-{month:02d}: {len(normalized)} registros")

            return normalized

        except RequestException as exc:
            message = f"Erro de requisição em {year}-{month:02d}: {exc}"
            logger.error(message)
            self.stats["erros"].append((year, month, str(exc)))
            return []

        except Exception as exc:
            message = f"Erro inesperado em {year}-{month:02d}: {exc}"
            logger.error(message)
            self.stats["erros"].append((year, month, str(exc)))
            return []

    def fetch_vigencia_records(self, year: int) -> List[Dict[str, Any]]:
        """Fluxo alternativo para endpoints que usam ano de início de vigência."""
        raise NotImplementedError(
            f"{self.__class__.__name__} precisa implementar fetch_vigencia_records(year) "
            "quando period_mode == 'ano_inicio_vigencia'."
        )

    def fetch_year_records(self, year: int) -> List[Dict[str, Any]]:
        """Extrai todos os registros de um ano.

        Implementação padrão: percorre todos os meses do ano. Quando o recurso usa
        "anoInicioVigencia" em vez de "ano/mes", o fluxo alternativo é acionado.
        """
        if self.period_mode == "ano_inicio_vigencia":
            return self.fetch_vigencia_records(year)

        all_records: List[Dict[str, Any]] = []
        for month in range(1, 13):
            all_records.extend(self.extract_month(year, month, verbose=False))
        return all_records

    def extract_year(self, year: int, verbose: bool = True) -> Tuple[List[Dict[str, Any]], int]:
        """Extrai todos os registros do ano informado."""
        if not self.validate_period(year):
            return [], 0

        logger.info(f"\n{'=' * 60}")
        logger.info(f"Processando ano {year}")
        logger.info(f"{'=' * 60}")

        raw_records = self.fetch_year_records(year)
        all_records = self.unwrap_records(raw_records)

        self.stats["total_registros"] += len(all_records)
        self.stats["anos_processados"].append(year)

        logger.info(f"Total para {year}: {len(all_records)} registros")

        return all_records, len(all_records)

    def extract_period(
        self,
        year_start: int,
        year_end: int,
        verbose: bool = True,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Extrai todos os registros em um intervalo de anos."""
        if year_start > year_end:
            logger.error("Ano inicial deve ser menor ou igual ao ano final")
            return [], 0

        all_records: List[Dict[str, Any]] = []

        for year in range(year_start, year_end + 1):
            records, _ = self.extract_year(year, verbose=verbose)
            all_records.extend(records)

        return all_records, len(all_records)

    def extract_and_save_year(
        self,
        year: int,
        verbose: bool = True,
        formats: Optional[List[str]] = None,
        include_report: bool = True,
    ) -> Dict[str, Any]:
        """Extrai um ano e salva imediatamente em disco."""
        records, total = self.extract_year(year=year, verbose=verbose)
        files = self.save_records(
            records=records,
            year=year,
            formats=formats,
            include_report=include_report,
        )
        return {
            "total_registros": total,
            "arquivos": files,
            "dados": records,
        }

    def extract_and_save_period(
        self,
        year_start: int,
        year_end: int,
        verbose: bool = True,
        formats: Optional[List[str]] = None,
        include_report: bool = True,
    ) -> Dict[str, Any]:
        """Extrai um intervalo de anos e salva os dados em disco."""
        records, total = self.extract_period(year_start=year_start, year_end=year_end, verbose=verbose)
        files = self.save_records(
            records=records,
            year=year_start,
            formats=formats,
            include_report=include_report,
        )
        return {
            "total_registros": total,
            "arquivos": files,
            "dados": records,
        }

    def _save_csv(self, df: pd.DataFrame, filename: str) -> Path:
        path = self.output_dir / filename
        df.to_csv(path, index=False, encoding="utf-8-sig")
        logger.info(f"CSV salvo: {path}")
        return path

    def _save_excel(self, df: pd.DataFrame, filename: str) -> Path:
        path = self.output_dir / filename

        try:
            with pd.ExcelWriter(path, engine="openpyxl") as writer:
                df.to_excel(writer, index=False, sheet_name="Dados")

                worksheet = writer.sheets["Dados"]
                for idx, column in enumerate(df.columns):
                    max_length = max(df[column].astype(str).str.len().max(), len(str(column)))
                    worksheet.column_dimensions[chr(65 + idx)].width = min(max_length + 2, 50)

            logger.info(f"Excel salvo: {path}")
            return path

        except ImportError:
            logger.warning("openpyxl não instalado; salvando como CSV")
            return self._save_csv(df, filename.replace(".xlsx", ".csv"))

    def _save_json(self, data: List[Dict[str, Any]], filename: str) -> Path:
        path = self.output_dir / filename

        with open(path, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2, default=str)

        logger.info(f"JSON salvo: {path}")
        return path

    def _write_report(self, df: pd.DataFrame, base_name: str) -> Path:
        path = self.output_dir / f"{base_name}_relatorio.txt"

        with open(path, "w", encoding="utf-8") as handle:
            handle.write("=" * 60 + "\n")
            handle.write(f"RELATÓRIO DE EXTRAÇÃO - {self.resource_name.upper()}\n")
            handle.write("=" * 60 + "\n\n")
            handle.write(f"Data/Hora: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            handle.write(f"Total de registros: {len(df)}\n")
            handle.write(f"Tamanho em memória: {df.memory_usage(deep=True).sum() / 1024**2:.2f} MB\n\n")
            handle.write("COLUNAS:\n")
            handle.write("-" * 60 + "\n")

            for column in df.columns:
                dtype = df[column].dtype
                nulls = df[column].isna().sum()
                handle.write(f"  {column}: {dtype} ({nulls} nulos)\n")

            handle.write("\nESTATÍSTICAS:\n")
            handle.write("-" * 60 + "\n")
            handle.write(df.describe(include="all").to_string())

            handle.write("\n\nERROS ENCONTRADOS:\n")
            handle.write("-" * 60 + "\n")
            if self.stats["erros"]:
                for year, month, error in self.stats["erros"]:
                    handle.write(f"  {year}-{month:02d}: {error}\n")
            else:
                handle.write("  Nenhum erro!\n")

        logger.info(f"Relatório salvo: {path}")
        return path

    def save_records(
        self,
        records: List[Dict[str, Any]],
        year: int,
        formats: Optional[List[str]] = None,
        include_report: bool = True,
    ) -> Dict[str, Path]:
        """Salva os registros em CSV, Excel e/ou JSON."""
        normalized_records = self.unwrap_records(records)

        if not normalized_records:
            logger.warning(f"Nenhum dado para salvar do ano {year}")
            return {}

        formats = formats or ["csv"]
        df = pd.DataFrame(normalized_records)
        output: Dict[str, Path] = {}
        base_name = f"{self.resource_name}_{year}"

        for fmt in formats:
            try:
                lower = fmt.lower()
                if lower == "csv":
                    output["csv"] = self._save_csv(df, f"{base_name}.csv")
                elif lower == "excel":
                    output["excel"] = self._save_excel(df, f"{base_name}.xlsx")
                elif lower == "json":
                    output["json"] = self._save_json(records, f"{base_name}.json")
                else:
                    logger.warning(f"Formato desconhecido: {fmt}")
            except Exception as exc:
                logger.error(f"Erro ao salvar {fmt}: {exc}")

        if include_report and not df.empty:
            self._write_report(df, base_name)

        return output

    def process_period(
        self,
        year_start: int,
        year_end: int,
        formats: Optional[List[str]] = None,
        include_report: bool = True,
        save_by_year: bool = True,
    ) -> Dict[str, Any]:
        """Processa um período inteiro e salva os resultados por ano e consolidados."""
        formats = formats or ["csv"]
        results: Dict[str, Any] = {}
        all_records: List[Dict[str, Any]] = []

        for year in range(year_start, year_end + 1):
            records, total = self.extract_year(year, verbose=True)
            all_records.extend(records)

            if save_by_year and records:
                logger.info(f"Salvando dados de {year}...")
                files = self.save_records(records, year, formats=formats, include_report=include_report)
                results[year] = {"total_registros": total, "arquivos": files}

        if all_records and year_end - year_start > 0:
            logger.info(f"Salvando dados consolidados ({year_start}-{year_end})...")
            period_name = f"{year_start}_{year_end}"
            files = self.save_records(all_records, int(period_name.split("_")[0]), formats=formats, include_report=include_report)
            results["consolidado"] = {"total_registros": len(all_records), "arquivos": files}

        return results

    def show_summary(self) -> None:
        """Exibe um resumo simples da execução."""
        print("\n" + "=" * 60)
        print(" RESUMO DE EXTRAÇÃO")
        print("=" * 60)
        print(f"Total de registros: {self.stats['total_registros']:,}")
        print(f"Anos processados: {len(self.stats['anos_processados'])}")

        if self.stats["anos_processados"]:
            print(f"  • {', '.join(map(str, sorted(self.stats['anos_processados'])))}")

        print(f"Erros encontrados: {len(self.stats['erros'])}")
        if self.stats["erros"]:
            for year, month, error in self.stats["erros"][:5]:
                print(f"  • {year}-{month:02d}: {error[:50]}...")

        print("=" * 60 + "\n")

