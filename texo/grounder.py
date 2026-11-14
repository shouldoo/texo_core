"""
Texo Semantic Grounder: deterministic grounding of natural language ERP queries
into model, domain and fields for Odoo (search_read).
"""

import calendar
import json
import os
import re
from datetime import date
from typing import Any, Dict, List, Optional


class OdooSemanticGrounder:
    ALLOWED_OPERATORS = {"=", "!=", ">", "<", ">=", "<=", "in", "not in", "ilike", "=ilike", "like"}

    MONTHS_IT = {
        "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4,
        "maggio": 5, "giugno": 6, "luglio": 7, "agosto": 8,
        "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12
    }

    def __init__(self, catalog_path: Optional[str] = None):
        if not catalog_path:
            catalog_path = os.path.join(os.path.dirname(__file__), "catalog.json")
        with open(catalog_path, "r", encoding="utf-8") as f:
            self.catalog = json.load(f).get("models", {})

    def resolve_temporal(self, text: str, date_field: str, ref_date: Optional[date] = None) -> List[List[Any]]:
        if not date_field:
            return []

        if ref_date is None:
            ref_date = date.today()

        cur_year = ref_date.year
        cur_month = ref_date.month
        t = text.lower()

        # 1. Mese specifico (es. 'a Novembre', 'di Novembre', 'a Novembre 2026')
        for m_name, m_idx in self.MONTHS_IT.items():
            pattern = rf"\b(?:a|in|di|del mese di)\s+{m_name}(?:\s+(\d{{4}}))?\b"
            m = re.search(pattern, t)
            if m:
                year = int(m.group(1)) if m.group(1) else cur_year
                last_day = calendar.monthrange(year, m_idx)[1]
                start_str = f"{year:04d}-{m_idx:02d}-01 00:00:00"
                end_str = f"{year:04d}-{m_idx:02d}-{last_day:02d} 23:59:59"
                return [
                    [date_field, ">=", start_str],
                    [date_field, "<=", end_str]
                ]

        # 2. 'quest'anno' o 'anno corrente'
        if "quest'anno" in t or "quest anno" in t or "anno corrente" in t:
            return [
                [date_field, ">=", f"{cur_year:04d}-01-01 00:00:00"],
                [date_field, "<=", f"{cur_year:04d}-12-31 23:59:59"]
            ]

        # 3. 'anno scorso'
        if "anno scorso" in t or "anno precedente" in t:
            prev_year = cur_year - 1
            return [
                [date_field, ">=", f"{prev_year:04d}-01-01 00:00:00"],
                [date_field, "<=", f"{prev_year:04d}-12-31 23:59:59"]
            ]

        # 4. 'questo mese'
        if "questo mese" in t:
            last_day = calendar.monthrange(cur_year, cur_month)[1]
            return [
                [date_field, ">=", f"{cur_year:04d}-{cur_month:02d}-01 00:00:00"],
                [date_field, "<=", f"{cur_year:04d}-{cur_month:02d}-{last_day:02d} 23:59:59"]
            ]

        return []

    def match_model(self, text: str) -> Optional[str]:
        t_lower = text.lower()

        # 1. Regole prioritarie specifiche
        if any(w in t_lower for w in ["task", "attività", "attivita", "compiti", "ticket"]):
            return "project.task"
        if any(w in t_lower for w in ["ddt", "bolla", "bolle", "spedizion", "consegn", "ricezion"]):
            return "stock.picking"
        if any(w in t_lower for w in ["prodott", "articol", "listin", "giacenz"]):
            return "product.template"
        if "fattur" in t_lower or "nota di credito" in t_lower or "note di credito" in t_lower:
            return "account.move"
        if "acquist" in t_lower or "rfq" in t_lower or ("fornitor" in t_lower and "ordin" in t_lower):
            return "purchase.order"
        if "ordin" in t_lower or "preventiv" in t_lower or "vendit" in t_lower:
            return "sale.order"
        if any(w in t_lower for w in ["client", "fornitor", "anagrafic", "contatt", "aziend"]):
            return "res.partner"

        # 2. Fallback su token
        tokens = set(re.findall(r"\b\w+\b", t_lower))
        best_model = None
        max_score = 0
        for model_name, spec in self.catalog.items():
            syns = set(spec.get("synonyms", []))
            common = tokens.intersection(syns)
            if len(common) > max_score:
                max_score = len(common)
                best_model = model_name

        return best_model

    def ground(self, text: str, ref_date: Optional[date] = None, limit: int = 20) -> Dict[str, Any]:
        model = self.match_model(text)
        if not model:
            raise ValueError(f"Impossibile identificare un modello Odoo per la richiesta: '{text}'")

        spec = self.catalog[model]
        domain: List[List[Any]] = []
        t_lower = text.lower()

        # 1. Filtri di business (ordinati per lunghezza decrescente)
        b_filters = spec.get("business_filters", {})
        sorted_kws = sorted(b_filters.keys(), key=len, reverse=True)
        matched_fields = set()

        for kw in sorted_kws:
            pattern = rf"\b{re.escape(kw)}\b"
            if re.search(pattern, t_lower):
                conds = b_filters[kw]
                cond_fields = {c[0] for c in conds}
                if not cond_fields.intersection(matched_fields):
                    for cond in conds:
                        if cond not in domain:
                            domain.append(cond)
                    matched_fields.update(cond_fields)

        # 2. Risoluzione temporale
        date_field = spec.get("date_field")
        if date_field:
            temporal_domain = self.resolve_temporal(text, date_field, ref_date=ref_date)
            domain.extend(temporal_domain)

        # 3. Filtri relazionali
        if model in ("sale.order", "account.move", "purchase.order", "stock.picking"):
            m_client = re.search(
                r"\b(?:del cliente|per il cliente|cliente"
                r"|dal fornitore|del fornitore|fornitore)\s+([A-Z][a-zA-Z0-9_\-]+)", text)
            if m_client:
                partner_name = m_client.group(1)
                if partner_name.lower() not in self.MONTHS_IT and partner_name.lower() not in ["oggi", "ieri"]:
                    domain.append(["partner_id.name", "ilike", partner_name])

        if model == "res.partner":
            m_city = re.search(r"\b(?:di|a|in)\s+([A-Z][a-zA-Z0-9_\-]+)\b", text)
            if m_city:
                city_name = m_city.group(1)
                if city_name.lower() not in self.MONTHS_IT and city_name.lower() not in ["oggi", "ieri"]:
                    domain.append(["city", "ilike", city_name])

        # 4. Selezione campi
        fields = list(spec.get("default_fields", ["id", "display_name"]))
        field_aliases = spec.get("field_aliases", {})
        for alias, real_field in field_aliases.items():
            if re.search(rf"\b{re.escape(alias)}\b", t_lower):
                if real_field not in fields:
                    fields.append(real_field)

        payload = {
            "model": model,
            "domain": domain,
            "fields": fields,
            "limit": limit
        }

        self.validate(payload)
        return payload

    def validate(self, payload: Dict[str, Any]) -> bool:
        model = payload.get("model")
        if model not in self.catalog:
            raise ValueError(f"Modello '{model}' non autorizzato o inesistente nel catalogo.")

        spec = self.catalog[model]
        allowed_fields = set(spec.get("allowed_fields", []))

        for fld in payload.get("fields", []):
            if fld not in allowed_fields:
                raise ValueError(f"Campo '{fld}' non consentito o inesistente su {model}.")

        for cond in payload.get("domain", []):
            if not isinstance(cond, (list, tuple)) or len(cond) != 3:
                raise ValueError(f"Tupla di dominio non valida: {cond}")
            fld, op, val = cond
            base_fld = fld.split(".")[0]
            if base_fld not in allowed_fields:
                raise ValueError(f"Campo di dominio '{fld}' sconosciuto su {model}.")
            if op not in self.ALLOWED_OPERATORS:
                raise ValueError(f"Operatore '{op}' non ammesso.")

        return True


_GLOBAL_GROUNDER = None

def get_grounder() -> OdooSemanticGrounder:
    global _GLOBAL_GROUNDER
    if _GLOBAL_GROUNDER is None:
        _GLOBAL_GROUNDER = OdooSemanticGrounder()
    return _GLOBAL_GROUNDER


def ground_query(text: str, ref_date: Optional[date] = None, limit: int = 20) -> Dict[str, Any]:
    return get_grounder().ground(text, ref_date=ref_date, limit=limit)
