from datetime import timedelta

from django.contrib.auth.hashers import make_password
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from .authentication import create_access_token
from .models import Event, Profile, Subtask
from .sanitizers import sanitize_text


class SanitizeTextTests(SimpleTestCase):
    def test_elimina_etiquetas_html(self):
        self.assertEqual(
            sanitize_text("Listo <script>alert(1)</script> y <b>revisado</b>"),
            "Listo alert(1) y revisado",
        )

    def test_elimina_caracteres_de_control_y_invisibles(self):
        self.assertEqual(sanitize_text("a\x00b\x07c\u200bd\u202ee\ufeff"), "abcde")

    def test_elimina_sustitutos_unicode_invalidos(self):
        self.assertEqual(sanitize_text("hola\ud800"), "hola")

    def test_conserva_saltos_de_linea_tildes_y_emojis_compuestos(self):
        self.assertEqual(
            sanitize_text("Línea 1\r\nLínea 2 👨‍👩‍👧"), "Línea 1\nLínea 2 👨‍👩‍👧"
        )

    def test_normaliza_espacios_y_saltos_repetidos(self):
        self.assertEqual(sanitize_text("  uno  \n\n\n\n dos \t\n"), "uno\n\n dos")

    def test_vacio_o_solo_etiquetas_devuelve_none(self):
        for value in ("", "   \n\t ", "<p></p>", "\x00\u200b"):
            self.assertIsNone(sanitize_text(value))


@override_settings(JWT_SECRET="isolated-subtask-notes-tests-secret-not-for-production")
class SubtaskPatchTests(TestCase):
    def setUp(self):
        self.today = timezone.localdate()
        self.a = Profile.objects.create(
            id="sn-a",
            name="SN A",
            email="sn-a@example.invalid",
            password_hash=make_password("testing-only"),
        )
        self.b = Profile.objects.create(
            id="sn-b",
            name="SN B",
            email="sn-b@example.invalid",
            password_hash=make_password("testing-only"),
        )
        self.event = Event.objects.create(
            user=self.a,
            name="Evento",
            type="Social",
            event_date=self.today + timedelta(days=30),
        )
        self.item = Subtask.objects.create(
            event=self.event, name="Gestión", estimated_hours=2, target_date=self.today
        )
        self.client = APIClient()
        self.client.credentials(
            HTTP_AUTHORIZATION="Bearer " + create_access_token(self.a.id)
        )

    def patch(self, data, item=None):
        return self.client.patch(
            "/subtasks/" + (item or self.item).id, data, format="json"
        )

    def test_nueva_subtarea_nace_pendiente_sin_notas(self):
        self.assertEqual((self.item.status, self.item.notes), ("Pendiente", None))
        self.assertIsNone(self.client.get("/subtasks/" + self.item.id).json()["notes"])

    def test_patch_estado_y_notas_juntos(self):
        response = self.patch({"status": "Ejecutada", "notes": "Se pagó el anticipo."})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            (response.json()["status"], response.json()["notes"]),
            ("Ejecutada", "Se pagó el anticipo."),
        )
        self.item.refresh_from_db()
        self.assertEqual(
            (self.item.status, self.item.notes), ("Ejecutada", "Se pagó el anticipo.")
        )

    def test_patch_solo_notas_no_cambia_el_estado(self):
        response = self.patch({"notes": "Llamar al proveedor"})
        self.assertEqual(response.status_code, 200)
        self.item.refresh_from_db()
        self.assertEqual(
            (self.item.status, self.item.notes), ("Pendiente", "Llamar al proveedor")
        )

    def test_estados_en_ingles_se_guardan_en_espanol(self):
        for sent, stored in (
            ("DONE", "Ejecutada"),
            ("postponed", "Pospuesta"),
            ("PENDING", "Pendiente"),
        ):
            response = self.patch({"status": sent})
            self.assertEqual(response.status_code, 200, response.content)
            self.assertEqual(response.json()["status"], stored)
            self.item.refresh_from_db()
            self.assertEqual(self.item.status, stored)

    def test_estado_invalido_devuelve_400_con_formato_global(self):
        response = self.patch({"status": "Cancelada"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "Revisa los campos marcados.")
        self.assertIn("status", response.json()["fields"])
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, "Pendiente")

    def test_notas_se_sanitizan_antes_de_guardar(self):
        response = self.patch(
            {"notes": "  <img src=x onerror=alert(1)>Entregado\x07\u200b "}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["notes"], "Entregado")
        self.item.refresh_from_db()
        self.assertEqual(self.item.notes, "Entregado")

    def test_caracter_nulo_se_rechaza_con_400(self):
        response = self.patch({"notes": "hola\x00"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("notes", response.json()["fields"])

    def test_notas_vacias_o_null_limpian_el_campo(self):
        self.patch({"notes": "algo"})
        for empty in ("", "   ", None, "<br>"):
            self.patch({"notes": "algo"})
            response = self.patch({"notes": empty})
            self.assertEqual(response.status_code, 200)
            self.assertIsNone(response.json()["notes"])
            self.item.refresh_from_db()
            self.assertIsNone(self.item.notes)

    def test_notas_en_el_limite_se_aceptan_y_por_encima_se_rechazan(self):
        self.assertEqual(
            self.patch({"notes": "a" * Subtask.NOTES_MAX_LENGTH}).status_code, 200
        )
        response = self.patch({"notes": "a" * (Subtask.NOTES_MAX_LENGTH + 1)})
        self.assertEqual(response.status_code, 400)
        self.assertIn("notes", response.json()["fields"])
        self.item.refresh_from_db()
        self.assertEqual(len(self.item.notes), Subtask.NOTES_MAX_LENGTH)

    def test_el_limite_se_mide_despues_de_sanitizar(self):
        padded = "<b></b>" * 100 + "a" * Subtask.NOTES_MAX_LENGTH + " " * 100
        self.assertEqual(self.patch({"notes": padded}).status_code, 200)

    def test_notas_con_tipo_incorrecto_devuelven_400(self):
        for bad in (["a"], {"a": 1}, True):
            response = self.patch({"notes": bad})
            self.assertEqual(response.status_code, 400, bad)
            self.assertIn("notes", response.json()["fields"])

    def test_cambiar_solo_notas_no_dispara_conflicto_de_capacidad(self):
        other = Event.objects.create(
            user=self.a, name="Otro", type="Social", event_date=self.event.event_date
        )
        Subtask.objects.create(
            event=other, name="Carga", estimated_hours=6, target_date=self.today
        )  # día ya sobrecargado
        response = self.patch({"notes": "Sin cambios de horario"})
        self.assertEqual(response.status_code, 200)

    def test_posponer_con_notas_conserva_fecha_y_horas(self):
        response = self.patch(
            {"status": "POSTPONED", "notes": "El cliente pidió esperar."}
        )
        self.assertEqual(response.status_code, 200)
        self.item.refresh_from_db()
        self.assertEqual(
            (self.item.status, self.item.target_date, float(self.item.estimated_hours)),
            ("Pospuesta", self.today, 2.0),
        )

    def test_otro_usuario_recibe_404_y_no_modifica_nada(self):
        self.client.credentials(
            HTTP_AUTHORIZATION="Bearer " + create_access_token(self.b.id)
        )
        response = self.patch({"status": "DONE", "notes": "intruso"})
        self.assertEqual(response.status_code, 404)
        self.item.refresh_from_db()
        self.assertEqual((self.item.status, self.item.notes), ("Pendiente", None))

    def test_sin_token_devuelve_401(self):
        self.client.credentials()
        self.assertEqual(self.patch({"notes": "x"}).status_code, 401)

    def test_listado_y_creacion_incluyen_notes(self):
        listing = self.client.get(f"/events/{self.event.id}/subtasks").json()
        self.assertIn(
            "notes", listing[0] if isinstance(listing, list) else listing["results"][0]
        )
        created = self.client.post(
            f"/events/{self.event.id}/subtasks",
            {
                "name": "Nueva",
                "target_date": str(self.today + timedelta(days=1)),
                "estimated_hours": 1,
                "notes": "<i>Con nota</i>",
                "status": "DONE",
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual(
            (created.json()["notes"], created.json()["status"]),
            ("Con nota", "Pendiente"),
        )
