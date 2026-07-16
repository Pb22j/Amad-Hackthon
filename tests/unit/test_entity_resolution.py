from dataclasses import dataclass

from agentic.tools.entity_resolution import resolve_entity


@dataclass(frozen=True)
class Person:
    name_ar: str
    name_en: str
    alias: str


PEOPLE = (
    Person("سعود عبدالله العنزي", "Saud Abdullah Alanazi", "سعود عبدالله"),
    Person("فيصل صالح الدوسري", "Faisal Saleh Aldosari", "فيصل"),
)


def _labels(person: Person) -> tuple[str, ...]:
    return person.name_ar, person.name_en, person.alias


def test_resolver_handles_partial_typo_transliteration_and_arabic_prefix():
    for query in ("سعود", "لسعود", "سعوود", "Saud", "Soud"):
        resolution = resolve_entity(query, PEOPLE, labels=_labels)
        assert resolution.match == PEOPLE[0]
        assert resolution.candidates == ()


def test_resolver_returns_close_ties_for_clarification_instead_of_guessing():
    people = PEOPLE + (
        Person("سعود محمد القحطاني", "Saud Mohammed Alqahtani", "سعود محمد"),
    )

    resolution = resolve_entity("سعود", people, labels=_labels)

    assert resolution.match is None
    assert set(resolution.candidates) == {people[0], people[2]}
    assert resolution.match_type == "ambiguous"


def test_resolver_does_not_match_a_middle_name_as_the_recipient():
    people = (
        Person("لطيفة محمد العنزي", "Latifa Mohammed Alanazi", "لطيفة"),
    )

    resolution = resolve_entity("محمد", people, labels=_labels)

    assert resolution.match is None
    assert resolution.candidates == ()
