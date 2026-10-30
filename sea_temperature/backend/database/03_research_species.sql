-- Names verified in the supplied research PDFs (not incidental species mentions):
-- cage_fish_research_full.pdf p15, D-1: the 11 named cage-fish targets.
-- gul_research_full.pdf p1; meongge_research_full.pdf p1;
-- styela_research_full.pdf p1: 굴, 멍게, 미더덕, 오만둥이.
-- Preserve existing IDs and customer links; add only missing catalogue names.
INSERT INTO customer_service.species (species_name)
VALUES
    ('조피볼락 (우럭)'),
    ('볼락'),
    ('참돔'),
    ('돌돔'),
    ('감성돔'),
    ('점농어'),
    ('말쥐치'),
    ('참쥐치'),
    ('가숭어'),
    ('능성어'),
    ('방어'),
    ('굴'),
    ('멍게'),
    ('미더덕'),
    ('오만둥이')
ON CONFLICT (species_name) DO NOTHING;
