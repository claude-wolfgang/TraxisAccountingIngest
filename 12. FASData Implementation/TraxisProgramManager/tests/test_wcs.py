"""Tests for tpm.wcs."""

from tpm.wcs import format_for_machinist


class TestFormatForMachinist:
    def test_stock_top_center(self):
        result = format_for_machinist("Stock Box Point", "Top Center")
        assert result == "X: Center, Y: Center, Z: Top of Stock"

    def test_model_box_point_top(self):
        result = format_for_machinist("Model Box Point", "Top Center")
        assert result == "X: Center, Y: Center, Z: Top of Part"

    def test_selected_point(self):
        result = format_for_machinist("Selected Point", None)
        assert result == "Selected Point"

    def test_both_none(self):
        assert format_for_machinist(None, None) is None

    def test_stock_bottom(self):
        result = format_for_machinist("Stock Box Point", "Bottom Center")
        assert result == "X: Center, Y: Center, Z: Bottom of Stock"

    def test_model_bottom(self):
        result = format_for_machinist("Model Box Point", "Bottom Center")
        assert result == "X: Center, Y: Center, Z: Bottom of Part"

    def test_left_near(self):
        result = format_for_machinist("Stock Box Point", "Top Left Near")
        assert "X: Left" in result
        assert "Y: Near Side" in result
        assert "Z: Top of Stock" in result

    def test_right_far(self):
        result = format_for_machinist("Stock Box Point", "Top Right Far")
        assert "X: Right" in result
        assert "Y: Far Side" in result

    def test_model_origin_passthrough(self):
        result = format_for_machinist("Model Origin", "Some Point")
        assert result == "Model Origin, Some Point"
