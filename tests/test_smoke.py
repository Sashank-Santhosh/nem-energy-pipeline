def test_packages_import():
    import dashboard
    import forecast
    import ingest

    assert ingest and forecast and dashboard
