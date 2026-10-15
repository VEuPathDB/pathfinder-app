# Site Selection Hints

## When to Use Component Sites

Use **component sites** (PlasmoDB, ToxoDB, etc.) when:
- User is working with a specific organism
- Faster query performance is needed
- Full organism-specific searches are required
- Working with specialized data tables

## When to Use the Portal

Use **VEuPathDB Portal** when:
- Comparing across multiple organisms
- User hasn't specified an organism
- Looking for orthologs across species
- Initial exploration before focusing

## Organism to Site Mapping

| Organism | Site |
|----------|------|
| Plasmodium (malaria) | PlasmoDB |
| Toxoplasma | ToxoDB |
| Cryptosporidium | CryptoDB |
| Giardia | GiardiaDB |
| Trypanosoma, Leishmania | TriTrypDB |
| Fungi (pathogenic) | FungiDB |
| Mosquito, tick, fly vectors | VectorBase |
| Human, mouse hosts | HostDB |

## Common Searches by Site

### PlasmoDB
- Genes by stage expression (blood, liver, mosquito)
- Genes by P. falciparum vs P. vivax comparison
- Genes by subcellular localization

### ToxoDB
- Genes by life cycle stage
- Genes by host cell localization
- Genes by CRISPR fitness scores

### TriTrypDB
- Genes by trypanosome life stage
- Genes by Leishmania species comparison
- Genes by organelle targeting

## Record Type Availability

Not all record types are available on all sites:
- **gene** - Every site except OrthoMCL
- **group** and **sequence** - OrthoMCL only: ortholog groups and the proteins in them
- **snp** - Limited availability
- **compound** - PlasmoDB, ToxoDB mainly
- **pathway** - Most sites

