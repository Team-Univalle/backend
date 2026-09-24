from django.test import SimpleTestCase

from .serializers import SubtaskSerializer


class EstimatedHoursTest(SimpleTestCase):
    """HU-02: estimated_hours debe ser un número mayor que 0."""

    def validar(self, horas):
        datos = {'name': 'Reservar salón', 'target_date': '2026-12-01', 'estimated_hours': horas}
        return SubtaskSerializer(data=datos)

    def test_horas_validas(self):
        self.assertTrue(self.validar(2).is_valid())
        self.assertTrue(self.validar('1.5').is_valid())

    def test_horas_en_cero(self):
        s = self.validar(0)
        self.assertFalse(s.is_valid())
        self.assertIn('estimated_hours', s.errors)

    def test_horas_negativas(self):
        s = self.validar(-2)
        self.assertFalse(s.is_valid())
        self.assertIn('estimated_hours', s.errors)

    def test_horas_no_numericas(self):
        s = self.validar('abc')
        self.assertFalse(s.is_valid())
        self.assertIn('estimated_hours', s.errors)
