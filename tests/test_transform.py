from src.worker.transform import clean_company, split_name, to_crm_record, to_warehouse_record


def test_split_name_two_parts():
    assert split_name("Ada Lovelace") == ("Ada", "Lovelace")


def test_split_name_single_word():
    assert split_name("Prince") == ("Prince", "")


def test_split_name_multiple_words_keeps_rest_as_last_name():
    assert split_name("Mary Jane Watson") == ("Mary", "Jane Watson")


def test_clean_company_defaults_to_unknown():
    assert clean_company(None) == "Unknown"
    assert clean_company("") == "Unknown"


def test_clean_company_title_cases_and_strips():
    assert clean_company("  acme corp  ") == "Acme Corp"


def test_to_crm_record_maps_fields():
    lead = {
        "external_id": "abc-123",
        "full_name": "Grace Hopper",
        "email": "Grace@Example.com",
        "company": "navy research",
        "source": "webform",
        "submitted_at": "2026-01-01T00:00:00+00:00",
    }
    record = to_crm_record(lead)
    assert record["external_id"] == "abc-123"
    assert record["first_name"] == "Grace"
    assert record["last_name"] == "Hopper"
    assert record["email"] == "grace@example.com"
    assert record["company"] == "Navy Research"


def test_to_warehouse_record_adds_synced_at():
    crm_record = {"external_id": "abc-123", "email": "grace@example.com"}
    warehouse_record = to_warehouse_record(crm_record)
    assert warehouse_record["external_id"] == "abc-123"
    assert "synced_at" in warehouse_record
