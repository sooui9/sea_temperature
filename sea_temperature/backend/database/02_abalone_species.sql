-- Catalogue data only. Do not relabel existing generic abalone/customer links.
INSERT INTO customer_service.species (species_name)
VALUES ('전복(육상)'), ('전복(해상)')
ON CONFLICT (species_name) DO NOTHING;
