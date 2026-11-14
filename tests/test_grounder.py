import unittest
from datetime import date

from texo.grounder import OdooSemanticGrounder, ground_query


class TestGrounder(unittest.TestCase):
    def setUp(self):
        self.ref_date = date(2026, 11, 9)

    def test_sale_order_grounding(self):
        res = ground_query("ordini confermati a Novembre", ref_date=self.ref_date)
        self.assertEqual(res["model"], "sale.order")
        self.assertIn(["state", "=", "sale"], res["domain"])
        self.assertIn(["date_order", ">=", "2026-11-01 00:00:00"], res["domain"])

    def test_account_move_grounding(self):
        res = ground_query("fatture clienti non pagate", ref_date=self.ref_date)
        self.assertEqual(res["model"], "account.move")
        self.assertIn(["move_type", "=", "out_invoice"], res["domain"])
        self.assertIn(["payment_state", "in", ["not_paid", "partial"]], res["domain"])

    def test_project_task_grounding(self):
        res = ground_query("task aperte in corso", ref_date=self.ref_date)
        self.assertEqual(res["model"], "project.task")
        self.assertIn(["is_closed", "=", False], res["domain"])
        self.assertIn(["state", "=", "01_in_progress"], res["domain"])

    def test_stock_picking_grounding(self):
        res = ground_query("spedizioni consegnate", ref_date=self.ref_date)
        self.assertEqual(res["model"], "stock.picking")
        self.assertIn(["state", "=", "done"], res["domain"])

    def test_product_grounding(self):
        res = ground_query("articoli esauriti", ref_date=self.ref_date)
        self.assertEqual(res["model"], "product.template")
        self.assertIn(["qty_available", "<=", 0], res["domain"])

    def test_unknown_field_rejected(self):
        grounder = OdooSemanticGrounder()
        with self.assertRaises(ValueError):
            grounder.validate({
                "model": "sale.order",
                "fields": ["name", "fake_field_from_hallucination"],
                "domain": []
            })

    def test_op_ask_dispatch(self):
        from unittest.mock import MagicMock

        from texo.hub import op_ask, op_query

        mock_hub = MagicMock()
        mock_hub.call.return_value = {"records": [{"id": 1, "name": "SO001"}]}

        res = op_ask(mock_hub, {"prompt": "ordini confermati a Novembre"})
        mock_hub.call.assert_called_once()
        call_args = mock_hub.call.call_args[0]
        self.assertEqual(call_args[0], "search_read")
        self.assertEqual(call_args[1]["model"], "sale.order")
        self.assertIn("grounded", res)

        # test op_query dispatching to op_ask
        mock_hub.reset_mock()
        op_query(mock_hub, {"ask": "fatture non pagate"})
        mock_hub.call.assert_called_once()
        self.assertEqual(mock_hub.call.call_args[0][1]["model"], "account.move")


if __name__ == "__main__":
    unittest.main()
