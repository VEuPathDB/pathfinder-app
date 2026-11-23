from strategist.platform.paths import API_DIR
from strategist_scripted.seeds.catalog import SEEDS_DIR, get_seeds_for_site


def test_the_catalog_reads_its_seeds_from_the_scripted_package() -> None:
    assert SEEDS_DIR.joinpath("plasmodb.json").is_file()
    assert {seed.site_id for seed in get_seeds_for_site("plasmodb")} == {"plasmodb"}


def test_the_strategist_package_ships_no_seed_data() -> None:
    data = API_DIR / "src" / "strategist" / "data"

    assert [(data / "seeds").exists(), (data / "organism_params.json").exists()] == [
        False,
        False,
    ]
