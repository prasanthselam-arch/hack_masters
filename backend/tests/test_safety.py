from app.services.safety import check_text, is_emergency, numbers_in, numbers_preserved, redact


def test_forbidden_advice_detected():
    assert not check_text("You should stop taking your medicines.").passed
    assert not check_text("Increase the dose of insulin.").passed
    assert not check_text("There is no need to see a doctor.").passed
    assert not check_text("This will cure your diabetes, guaranteed.").passed


def test_negated_advice_allowed():
    assert check_text("Do not stop your medicines without talking to your doctor.").passed
    assert check_text("Never skip your dose.").passed
    assert check_text("Please take your medicines as prescribed and discuss any concerns with your doctor.").passed


def test_number_grounding():
    allowed = numbers_in({"value": 10.2, "range": "13.0 - 17.0"})
    assert check_text("Your haemoglobin is 10.2 g/dL, below 13.0.", allowed).passed
    rep = check_text("Your haemoglobin is 9.8 g/dL.", allowed)
    assert not rep.passed and rep.ungrounded_numbers == ["9.8"]
    assert check_text("Take 1 tablet for 2-3 months.", allowed).passed


def test_redact_and_translation_numbers():
    assert redact("Your sugar is high. Stop taking your medicines now.") == "Your sugar is high."
    table = "Your medicines:\n\n| Medicine | When |\n| --- | --- |\n| Glycomet | 1-0-1 |\n\nStop taking your medicines now. Ask your doctor."
    assert redact(table) == "Your medicines:\n\n| Medicine | When |\n| --- | --- |\n| Glycomet | 1-0-1 |\n\nAsk your doctor."
    assert numbers_preserved("HbA1c 7.4% on 2026-02-03", "एचबीए1सी 7.4% 2026-02-03")
    assert not numbers_preserved("HbA1c 7.4%", "HbA1c 7.2%")


def test_emergency():
    assert is_emergency("I have chest pain since morning")
    assert is_emergency("मुझे सांस लेने में तकलीफ है")
    assert not is_emergency("What is my HbA1c?")
