"""The catalog of the grounder as data: the rules that choose a model, and the union of the catalogs of the
core, of the packs and of the working folder."""
import json
import sys
import unittest
from pathlib import Path

CORE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CORE))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_fabric import PACK, FabricCase  # noqa: E402

from texo import catalog, mount  # noqa: E402
from texo.grounder import OdooSemanticGrounder, ground_query  # noqa: E402

# the model the rules chose for each question when they were code (grounder.match_model before the catalog
# carried them): the catalog must choose the same
BEFORE = [
    ["i task aperti di questo mese", "project.task"], ["ordini dei fornitori in ritardo", "purchase.order"],
    ["fatture dei clienti", "account.move"], ["ordini di vendita", "sale.order"],
    ["le bolle di consegna dei prodotti", "stock.picking"], ["contatti delle aziende", "res.partner"],
    ["preventivi dei clienti", "sale.order"], ["rfq aperte", "purchase.order"],
    ["giacenze degli articoli", "product.template"], ["note di credito ai fornitori", "account.move"],
    ["ticket dei clienti", "project.task"], ["listino acquisti", "product.template"],
    ["ordini confermati a Novembre", "sale.order"], ["fatture clienti non pagate", "account.move"],
    ["task aperte in corso", "project.task"], ["spedizioni consegnate", "stock.picking"],
    ["articoli esauriti", "product.template"], ["offerte in corso", "sale.order"], ["partner italiani", None],
    ["quanto fa due più due", None], ["consegne ai clienti di Roma", "stock.picking"],
    ["acquisti di prodotti", "product.template"], ["anagrafica fornitori", "res.partner"],
    ["attività del cliente Rossi", "project.task"],
]


def entry(priority, match, **more):
    return {"description": "d", "priority": priority, "match": match, "allowed_fields": ["name"],
            "default_fields": ["name"], **more}


class TestCatalogRules(unittest.TestCase):

    def test_the_rules_as_data_choose_the_model_the_code_chose(self):
        grounder = OdooSemanticGrounder()
        for question, model in BEFORE:
            self.assertEqual(grounder.match_model(question), model, question)

    def test_an_alternative_needs_all_its_words_and_the_highest_priority_wins(self):
        models = {"res.partner": entry(10, [["fornitor"]]), "purchase.order": entry(30, [["fornitor", "ordin"]]),
                  "sale.order": entry(20, [["ordin"]])}
        self.assertEqual(catalog.match_model(models, "i Fornitori di Roma"), "res.partner")
        self.assertEqual(catalog.match_model(models, "ordini ai fornitori"), "purchase.order")
        self.assertEqual(catalog.match_model(models, "ordini di oggi"), "sale.order")
        self.assertIsNone(catalog.match_model(models, "il tempo di domani"))
        tied = {"a.first": entry(5, [["x"]]), "b.second": entry(5, [["x"]])}
        self.assertEqual(catalog.match_model(tied, "x"), "a.first", "at the same priority, the first of the catalog")

    def test_the_union_replaces_refuses_and_reports(self):
        core = {"sale.order": entry(20, [["ordin"]]), "project.task": entry(70, [["task"], ["ticket"]])}
        one = {"project.project": entry(65, [["progett"]]), "sale.order": entry(25, [["ordin"], ["offert"]])}
        two = {"sale.order": entry(20, [["commess"]]), "helpdesk.ticket": entry(70, [["ticket"]])}
        folder = {"project.task": entry(80, [["task"], ["lavorazion"]])}
        models, origin, problems = catalog.union([("core", "core", core), ("one", "pack", one), ("two", "pack", two),
                                                  ("this folder", "folder", folder)])
        self.assertEqual([level for level, _message in problems], ["error"])
        self.assertIn("the packs one and two both define sale.order", problems[0][1])
        self.assertEqual(origin["sale.order"], ("one", "pack"), "the first pack stays, the mount refuses anyway")
        self.assertEqual(origin["project.task"], ("this folder", "folder"), "the folder replaces the whole entry")
        self.assertEqual(catalog.match_model(models, "le lavorazioni di oggi"), "project.task")
        self.assertEqual(catalog.match_model(models, "progetti attivi"), "project.project")
        # the same entry in two packs is no conflict; a pack replaces the core without one
        same, _origin, problems = catalog.union([("core", "core", core), ("one", "pack", one), ("copy", "pack", one)])
        self.assertEqual(problems, [])
        self.assertEqual(same["sale.order"]["priority"], 25)
        # two models that answer the same words at the same priority: said, not refused
        _models, _origin, problems = catalog.union([("core", "core", core), ("two", "pack", {
            "helpdesk.ticket": entry(70, [["ticket"]])})])
        self.assertEqual([level for level, _message in problems], ["warning"])
        self.assertIn("project.task (core) and helpdesk.ticket (two) answer to ticket at the same priority 70",
                      problems[0][1])

    def test_an_entry_in_the_wrong_form_is_said(self):
        self.assertEqual(catalog.entry_problems("x.model", entry(1, [["a", "b"], ["c"]])), [])
        for wrong in (entry("high", [["a"]]), entry(1, ["a"]), entry(1, [[]]), entry(1, [["a", 3]]),
                      entry(1, [["a"]], allowed_fields=[]), entry(1, [["a"]], synonyms="ordini"),
                      entry(1, [["a"]], business_filters=[]), "not an object"):
            self.assertTrue(catalog.entry_problems("x.model", wrong), wrong)
        self.assertEqual(catalog.core_models().keys(), OdooSemanticGrounder().catalog.keys())
        for model, core_entry in catalog.core_models().items():
            self.assertEqual(catalog.entry_problems(model, core_entry), [], model)


class TestCatalogOfAFolder(FabricCase):
    """What the packs and the folder add reaches the grounder through texo mount."""

    def pack(self, name, models):
        folder = self.tmp / "dev" / "packs" / name
        folder.mkdir(parents=True)
        (folder / "pack.toml").write_text(PACK.replace('"bakery"', f'"{name}"'))
        if models is not None:
            (folder / "catalog.json").write_text(json.dumps({"models": models}))
        toml = self.root / "texo.toml"
        toml.write_text(toml.read_text() + f'\n[[pack]]\nname = "{name}"\nversion = "v1.2.0"\npath = "{folder}"\n')
        return folder

    def test_a_pack_and_the_folder_add_their_models(self):
        self.pack("helpdesk", {"helpdesk.ticket": entry(75, [["ticket"], ["segnalazion"]], synonyms=["ticket"])})
        (self.root / "texo.catalog.json").write_text(json.dumps({"models": {
            "project.task": dict(catalog.core_models()["project.task"], priority=80,
                                 match=[["task"], ["lavorazion"]])}}))
        code, out = self.mount()
        self.assertEqual(code, 0, out)
        self.assertIn("[ok] catalog: helpdesk.ticket (helpdesk), project.task (this folder)", out)
        kept = json.loads((self.root / ".texo" / "catalog.json").read_text())
        self.assertEqual(sorted(kept["models"]), ["helpdesk.ticket", "project.task"], "only what is added")
        self.assertEqual(kept["origin"], {"helpdesk.ticket": "helpdesk", "project.task": "this folder"})
        grounder = OdooSemanticGrounder(root=self.root)
        self.assertEqual(grounder.match_model("i ticket dei clienti"), "helpdesk.ticket", "the pack's, above the core's")
        self.assertEqual(grounder.match_model("le lavorazioni di oggi"), "project.task", "the folder's entry")
        self.assertEqual(grounder.match_model("fatture dei clienti"), "account.move", "the core's stay")
        self.assertEqual(ground_query("le segnalazioni aperte", root=self.root)["model"], "helpdesk.ticket")
        self.assertEqual(OdooSemanticGrounder().match_model("i ticket dei clienti"), "project.task",
                         "outside the folder, the core alone")
        # the pack gives its catalog up: the file of the folder goes with what it held
        (self.tmp / "dev" / "packs" / "helpdesk" / "catalog.json").unlink()
        (self.root / "texo.catalog.json").unlink()
        self.mount()
        self.assertFalse((self.root / ".texo" / "catalog.json").exists())

    def test_two_packs_that_define_the_same_model_differently_mount_nothing(self):
        self.pack("helpdesk", {"support.ticket": entry(75, [["ticket"]])})
        self.pack("service", {"support.ticket": entry(75, [["assistenz"]])})
        code, out = self.mount()
        self.assertEqual(code, 1, out)
        self.assertIn("the packs helpdesk and service both define support.ticket", out)
        self.assertIn("Nothing mounted", out)
        # the folder decides with its own entry
        (self.root / "texo.catalog.json").write_text(json.dumps({"models": {
            "support.ticket": entry(75, [["ticket"], ["assistenz"]])}}))
        code, out = self.mount()
        self.assertEqual(code, 0, out)
        self.assertIn("[ok] catalog: support.ticket (this folder)", out)
        self.assertEqual(OdooSemanticGrounder(root=self.root).match_model("assistenza clienti"), "support.ticket")

    def test_a_tie_is_a_warning_and_a_broken_catalog_an_error(self):
        self.pack("helpdesk", {"helpdesk.ticket": entry(70, [["ticket"]])})
        code, out = self.mount()
        self.assertEqual(code, 0, out)
        self.assertIn("[warning] catalog: project.task (core) and helpdesk.ticket (helpdesk) answer to ticket", out)
        (self.root / "texo.catalog.json").write_text("{not json")
        code, out = self.mount()
        self.assertEqual(code, 1)
        self.assertIn("texo.catalog.json cannot be read", out)
        (self.root / "texo.catalog.json").write_text(json.dumps({"models": {"x.model": {"match": "ticket"}}}))
        code, out = self.mount()
        self.assertEqual(code, 1)
        self.assertIn("x.model: match is a list of alternatives", out)
        self.assertEqual(mount.MOUNTED, 0)


if __name__ == "__main__":
    unittest.main()
