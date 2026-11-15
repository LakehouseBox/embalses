"""Cantábrico Oriental river-basin plan 2022-2027: which supply unit serves each municipality, and where it takes
its water.

Source: Plan Hidrológico de la Demarcación Hidrográfica del Cantábrico Oriental, revisión de tercer ciclo 2022-2027
(Real Decreto 35/2023), Anejo VI "Asignación y reserva de recursos". One joint document covers the Basque
intra-community basins (URA) and the state part (CHC); the copies published by both are byte-identical:
  https://euskadi.eus/contenidos/informacion/plan_hidrologico_2022_2027/es_def/adjuntos/Anejo-06_Asignacion-y-reserva-de-recursos_20230124.pdf
  https://www.chcantabrico.es/documents/d/guest/anejo-vi-asignacion-y-reserva-de-recursos-3
For each of the eight exploitation systems the annex has
  - a table "Valores anuales de demanda para las UDUs incluidas en el modelo": UDU name | municipalities included,
    some with the share of the municipality the unit serves ("Amurrio (91%)");
  - a table "Asignación y reserva de recursos": per UDU, up to three origins with their % of the allocation
    ("Trasvase Zadorra 88 %", "Embalse de Undurraga 12 %"), plus footnotes on emergency sources;
  - narrative describing each system's intakes (springs, boreholes, reservoirs).
The plan gives the UDUs no codes; unit codes here are a system prefix plus the order of the demand table (IBB01…).
Municipalities and units are written out below from the demand tables; the script checks that every unit name and
municipality string is printed in the annex, reads the allocation tables from the PDF, and types each origin with
ORIGINS (origin label as printed -> sources). Units missing from the allocation tables take their sources from the
narrative (NARRATIVE), each with a short quotation the script finds in the PDF to cite its page.

Writes, into OUT_DIR (default data/raw/plans/cantabrico_oriental): meta.json, supply_units.csv,
municipality_supply.csv, supply_sources.csv, unmatched.csv (format: tools/supply_plans_format.md).

Usage: uv run --with pdfplumber python tools/extract_supply_cantabrico_oriental.py [OUT_DIR]
"""
import csv
import json
import os
import re
import sys
import unicodedata
import urllib.request

import pdfplumber

URL = ("https://euskadi.eus/contenidos/informacion/plan_hidrologico_2022_2027/es_def/adjuntos/"
       "Anejo-06_Asignacion-y-reserva-de-recursos_20230124.pdf")
PDF_NAME = "Anejo-06_Asignacion-y-reserva-de-recursos_20230124.pdf"
REFERENCE = "data/raw/ine/municipalities_reference.csv"
PROVINCES = ("01", "20", "48", "31", "09", "39")      # Araba, Gipuzkoa, Bizkaia, Navarra, Burgos, Cantabria

# Demand tables, in the order printed: (system prefix, system), then (unit name as printed, "municipalities as printed").
# A municipality with "(nn%)" is served by the unit only in that share.
UNITS = [
    ("IBB", "Ibaizabal-Butroe-Barbadun", [
        ("Zadorra-Gran Bilbao", "Arrigorriaga, Basauri, Etxebarri, Zarátamo, Ugao-Miraballes, Larrabetzu, Lezama, "
         "Zamudio, Derio, Loiu, Sondika, Erandio, Leioa, Berango, Getxo, Sopelana, Barrika, Plentzia, Gorliz, Lemoiz, "
         "Maruri-Jatabe, Gatika, Laukiz, Urduliz, Mungia, Gamiz-Fika, Morga, Fruiz, Abanto-Ciérvana, Zierbena, Muskiz, "
         "Santurtzi, Portugalete, Ortuella, Trapagaran, Alonsotegi, Bedia, Lemoa, Galdakao, Zeberio, Ubide, "
         "Galdames (87%), Sopuerta (98%)"),
        ("Bilbao", "Bilbao"),
        ("Barakaldo-Sestao", "Barakaldo, Sestao"),
        ("Ordunte (excepto Bilbao)", "Güeñes, Zalla, Balmaseda, Gordexola (91%)"),
        ("Gordexola", "Gordexola (9%)"),
        ("Duranguesado", "Atxondo, Mañaria, Izurtza, Zaldibar, Durango, Iurreta, Elorrio (96%)"),
        ("Mallabia", "Mallabia"),
        ("Berriz", "Berriz"),
        ("Abadiño", "Abadiño (99,5%)"),
        ("Garai", "Garai"),
        ("Amorebieta", "Amorebieta"),
        ("Valle Arratia", "Dima, Igorre, Zeanuri, Areatza, Arantzazu, Artea"),
        ("Orozko-parcial", "Orozko (98%)"),
        ("Arakaldo-Arrankudiaga (parcial)", "Arakaldo, Arrankudiaga (11%)"),
        ("Arane (Arrank)", "Arrankudiaga (77%)"),
        ("Orduña", "Orduña"),
        ("Alto Nervión", "Llodio, Amurrio (91%), Ayala/Aiara (85%)"),
        ("Artziniega", "Artziniega"),
        ("Okondo", "Okondo"),
        ("Lezama (Amurrio)", "Amurrio (3%)"),
        ("Larrinbe (Amurrio)", "Amurrio (2%)"),
        ("Bakio", "Bakio"),
        ("Meñaka", "Meñaka"),
        ("AMVISA", "Vitoria (99,9%), Arrazua-Ubarrundia (86%), Legutiano (14%)"),
    ]),
    ("OKA", "Oka", [
        ("Ibarrangelua-Elantxobe", "Ibarrangelua, Elantxobe"),
        ("Sist_Gernika", "Gautegiz-Arteaga, Gernika-Lumo, Muxika (72%), Kortezubi, Ajangiz, Arratzu"),
        ("Forua-Murueta", "Forua, Murueta"),
        ("Buspemun", "Mundaka, Sukarrieta, Busturia"),
        ("Bermeo", "Bermeo"),
        ("Mendata", "Mendata"),
        ("Ereño", "Ereño"),        # allocation table and narrative only (sistema Ereño), not in the demand table
    ]),
    ("LEA", "Lea-Artibai", [
        ("Markina y otros", "Munitibar-Arbatzegi Gerrikaitz, Aulesti (87%), Etxebarria, Ziortza-Bolibar, Markina (96%)"),
        ("Amoroto", "Amoroto (83%)"),
        ("Gizaburuaga", "Gizaburuaga"),
        ("Ispaster", "Ispaster (86%)"),
        ("Lekeitio y otros", "Lekeitio, Ispaster (14%), Amoroto (17%), Mendexa, Berriatua (15%)"),
        ("Ondarroa", "Ondarroa"),
        ("Berriatua", "Berriatua (85%)"),
        ("Ea", "Ea"),
    ]),
    ("DEB", "Deba", [
        ("Arrasate", "Arrasate"),
        ("Alto Deba", "Aretxabaleta, Elgeta, Eskoriatza, Soraluze, Oñati (95%)"),
        ("Bergara", "Bergara"),
        ("Antzuola", "Antzuola"),
        ("Oñati_parcial", "Oñati (4%)"),
        ("Leintz-Gatzaga", "Leintz-Gatzaga"),
        ("Aramaio_parcial", "Aramaio (21%)"),
        ("Ermua", "Ermua"),
        ("Eibar", "Eibar"),
        ("Kilimon", "Elgoibar, Mendaro, Mutriku, Deba (81%)"),
        ("Deba y Zestoa_parcial", "Zestoa (1%), Deba (19%)"),
    ]),
    ("URO", "Urola", [
        ("Barrendiola", "Legazpi, Urretxu, Zumarraga, Ezkio-Itsaso"),
        ("Ibaieder", "Azkoitia, Azpeitia, Zestoa, Aizarnazabal, Zumaia, Getaria, Orio, Zarautz, Aia (39%)"),
        ("Errezil_Artzallus", "Errezil (43%)"),
    ]),
    ("ORI", "Oria", [
        ("Ataun", "Ataun"),
        ("Alto Oria", "Beasain, Idiazabal, Lazkao (30%), Olaberria, Ordizia (97%), Ormaiztegi, Segura, Gaintza, Mutiloa, "
         "Zerain, Zegama, Gabiria, Altzaga, Itsasondo, Legorreta, Arama, Abaltzisketa, Orendain, Baliarrain"),
        ("Oria Medio", "Ikaztegieta, Alegia, Altzo, Tolosa, Ibarra, Belauntza, Anoeta, Irura, Billabona, Zizurkil, "
         "Asteasu (90%), Andoain, Aduna, Leaburu"),
        ("Ordizia resto", "Ordizia (3%)"),
        ("Zaldibia", "Zaldibia"),
        ("Amezketa", "Amezketa"),
        ("Albiztur", "Albiztur"),
        ("Berrobi", "Berrobi"),
        ("Urnieta-Goiburu", "Urnieta (8,5%)"),
        ("Aia", "Aia (47%)"),
    ]),
    ("URU", "Urumea-Oiartzun", [
        ("Añarbe", "Urnieta, Hernani (97%), Astigarraga, Donostia, Errenteria, Lasarte-Oria, Pasaia (86%), Lezo (94%)"),
        ("Oiartzun_Karrika", "Oiartzun (2,7%)"),
        ("Oiartzun resto", "Oairtzun (97,3%)"),
        ("Usurbil", "Usurbil"),
    ]),
    ("BID", "Bidasoa", [
        ("Baztán", "Baztán"),
        ("Bera", "Bera"),
        ("Bertizarana", "Bertizarana"),
        ("Doña María", "Doña María"),
        ("Doneztebe", "Doneztebe"),
        ("Lesaka", "Lesaka"),
        ("Malerreka", "Ituren, Zubieta, Elgorriaga, Sunbilla"),
        ("Hondarribia e Irun", "Hondarribia (92%), Irun"),
        ("Urb. Jaizkibel", "Hondarribia (8%)"),
    ]),
]

# Plan spellings -> INE official names (only where the name alone does not match).
ALIASES = {
    "Abanto-Ciérvana": "Abanto y Ciérvana-Abanto Zierbena", "Trapagaran": "Valle de Trápaga-Trapagaran",
    "Sopelana": "Sopela", "Amorebieta": "Amorebieta-Etxano", "Arrankudiaga": "Arrankudiaga-Zollo",
    "Vitoria": "Vitoria-Gasteiz", "Arrazua-Ubarrundia": "Arratzua-Ubarrundia", "Legutiano": "Legutio",
    "Ibarrangelua": "Ibarrangelu", "Markina": "Markina-Xemein", "Soraluze": "Soraluze-Placencia de las Armas",
    "Oairtzun": "Oiartzun", "Doña María": "Donamaria", "Donostia": "Donostia/San Sebastián",
    "Doneztebe": "Doneztebe/Santesteban", "Billabona": "Villabona",
}
# Where a municipality appears in two units but the plan prints a share for only one, the other is its complement.
COMPLEMENT = {("Zestoa", "Ibaieder"): 99.0, ("Urnieta", "Añarbe"): 91.5}

# Allocation-table unit names that differ from the demand table.
ALLOC_NAMES = {"Berritua": "Berriatua", "Malaerreka": "Malerreka", "Urbanización Jaizkibel": "Urb. Jaizkibel",
               }

ZADORRA = [("transfer", "Zadorra", "main", "Zadorra system of the Consorcio de Aguas Bilbao Bizkaia: water from the "
            "Ullibarri-Ganboa and Urrunaga reservoirs (Ebro basin) carried by the Urrunaga-Undurraga transfer"),
           ("reservoir", "Ullibarri-Ganboa", "main", "Ebro-basin reservoir feeding the Zadorra transfer"),
           ("reservoir", "Urrunaga", "main", "Ebro-basin reservoir feeding the Zadorra transfer")]
SHARE_ON_FIRST = {"Trasvase Zadorra"}     # the % belongs to the transfer; the reservoirs behind it are context
GARAIZAR = [("aquifer", None, "main", "Duranguesado boreholes (Harrobia I-II, Gallandas A, A-bis and B, Arria A and B)"),
            ("river", None, "main", "surface intakes Markue and Arria-Patala"),
            ("spring", "Gallandas", "main", None), ("spring", "Mendiko", "main", None)]


def generic(where):
    return [("river", None, "main", f"intakes feeding {where}; the plan does not give their type")]


# Origin label as printed in the allocation tables -> sources (type, name, role, notes). A label that maps to one
# source passes its % on as share_pct; a label that maps to several gives the % in each row's notes.
ORIGINS = {
    "Trasvase Zadorra": ZADORRA,
    "Embalse de Undurraga": [("reservoir", "Undurraga", "main", "receives the Zadorra transfer")],
    "Embalses de Ordunte y Zollo": [("reservoir", "Ordunte", "main", None),
                                    ("reservoir", "Zollo", "backup", "complementary resource in an emergency")],
    "Embalses de Artiba, Loiola y Nocedal y captaciones a ETAP de Cruces": [
        ("reservoir", "Artiba", "main", None), ("reservoir", "Loiola", "backup", "not in service at present"),
        ("reservoir", "Nocedal", "main", None), ("river", None, "main", "intakes feeding ETAP de Cruces")],
    "Embalse de Ordunte y captaciones a ETAP de Sollano y ETAP de Salinillas": [
        ("reservoir", "Ordunte", "main", None),
        ("spring", None, "main", "springs of the La Cuadra (Bizagorta I-III, La Returilla) and Sodupe (Ereza I-III, "
         "La Cueva, Grazal Alto and Bajo) systems; the table names the ETAPs de Sollano and de Salinillas")],
    "Captaciones de San Juanales y Arroyo": [("spring", "San Juanales", "main", "springs San Juanales 1-6"),
                                             ("river", None, "main", "stream intake ('Arroyo')")],
    "Captaciones a ETAP de Garaizar": GARAIZAR,
    "Captaciones ETAP San Salvador": [("spring", "Garai", "main", "San Salvador system, ETAP San Salvador")],
    "Captaciones de Zengoitia 1 y 2": [("river", "Zengoitia", "main", "intakes Zengoitia 1 and 2")],
    "Captaciones al dep. de San Lorenzo": [
        ("spring", None, "main", "springs Laguen 1-5, Oka, Urdelatz and Urcelai"),
        ("aquifer", "Oizetxebarrieta", "main", "borehole")],
    "Captaciones a depósito de Garai": [("spring", "Urzulo", "main", None)],
    "Captaciones a ETAP de Urritxe": [("river", None, "main", "surface intakes feeding ETAP de Urritxe"),
                                      ("spring", "Berroetas", "main", None),
                                      ("aquifer", "Etxano", "main", "borehole")],
    "Captaciones a ETAP de San Cristóbal": generic("ETAP de San Cristóbal"),
    "Captaciones a la ETAP de Ibarra": generic("ETAP de Ibarra"),
    "Captaciones al depósito de Goikiri": [("spring", "Petxabi", "main", None),
                                          ("aquifer", "Ziliku", "main", "borehole")],
    "Captaciones al depósito de Zabale": generic("the Zabale tank (Arene-Uribarri and Urdiola systems)"),
    "Captaciones a la balsa y ETAP de Gartxeta": [
        ("spring", None, "main", "springs Lendoñogoiti 1-2, Lendoñobeiti, Lateta and La Choza, stored in the "
         "Gartxeta pond")],
    "Embalse de Maroño": [("reservoir", "Maroño", "main", None)],
    "Captación de Altube-Bestialde": [("river", "Altube-Bestialde", "main", None)],
    "Captaciones a la ETAP de Aspuru": generic("ETAP de Aspuru"),
    "Embalse de Artziniega": [("reservoir", "Artziniega", "main", None)],
    "Captaciones a ETAP de Okondo": generic("ETAP de Okondo"),
    "Captaciones al depósito de Lezama": generic("the Lezama tank"),
    "Captaciones a la ETAP de Iperraga": [("aquifer", "Berganza", "main", "borehole of the Larrinbe system")],
    "Captaciones a la ETAP de San Miguel": generic("ETAP de San Miguel"),
    "Captaciones al dep. de Santillandi": [("aquifer", "Santillandi", "main", "borehole"),
                                           ("aquifer", "Arkaitxiki", "main", "borehole")],
    "Captaciones a ETAP de Burgoa": [("river", "río Oka", "main", None), ("spring", "Rekalde", "main", None),
                                     ("spring", "Oxiña", "main", None),
                                     ("aquifer", "Vega III", "main", "borehole"),
                                     ("aquifer", "Olalde", "main", "borehole in the Ereñozar groundwater body")],
    "Captaciones a ETAP de Forua": [("spring", "Atxakozulo", "main", None)],
    "Captaciones a ETAP de Busturia": generic("ETAP de Busturia"),
    "Captaciones de margen izquierda de río Oka a ETAP de Bermeo": [
        ("river", None, "main", "intakes on the left bank of the río Oka, to ETAP de Bermeo")],
    "Captaciones de margen derecha de río Oka a ETAP de Bermeo": [
        ("river", None, "main", "intakes on the right bank of the río Oka, to ETAP de Bermeo")],
    "Captaciones a ETAP de Mendata": [("river", None, "main", "intakes feeding ETAP de Mendata"),
                                      ("aquifer", "Magunas", "main", "borehole")],
    "Manantiales Bollar y Apaizene": [("spring", "Bollar", "main", None), ("spring", "Apaizene", "main", None)],
    "Captaciones en UH Artibai a ETAP de Iparraguirre": [
        ("spring", None, "main", "Artibai springs Muniategi, Aranbaltza, Alcibar, Iterixa, Urko, Altzolabarri, "
         "Arrimurriaga I-II, Arnoriaga, Gandianagusia, Oiz I-II"),
        ("aquifer", "Ibazeta", "main", "borehole")],
    "Captaciones en UH Lea a ETAP de Iparraguirre": [("spring", None, "main", "Lea springs Iñuzi and Muxo")],
    "Captaciones a ETAP de Telleria": [("river", None, "main", "intakes feeding ETAP de Telleria"),
                                       ("aquifer", "Okamika", "main", "borehole")],
    "Captaciones a ETAP de Bertxia": [("spring", "Argin", "main", None), ("aquifer", "Aboitiz", "main", "borehole")],
    "Río Lea": [("river", "río Lea", "main", None)],
    "Balsa de Zulueta": [("reservoir", "Zulueta", "backup", "small pond on the arroyo Zulueta, used when the main "
                          "intake falls short")],
    "Captaciones de Kortezierra y Baboliña": [("spring", "Kortezierra", "main", None),
                                              ("spring", "Baboliña", "main", None)],
    "Captaciones a ETAP de Gorozika": generic("ETAP de Gorozika"),
    "Captaciones a ETAP de Montegane": generic("ETAP de Montegane"),
    "Captaciones a ETAP de Ea": generic("ETAP de Ea"),
    "Embalse de Urkulu y captación a embalse": [("reservoir", "Urkulu", "main", "also receives the Bolibar weir transfer")],
    "Manantial Beneras": [("spring", "Beneras", "main", None)],
    "Galería Urtzulo": [("spring", "Urtzulo", "main", "gallery")],
    "Manantial Olaun": [("spring", "Olaun", "main", None)],
    "Sondeos San Asensio y San Adrián": [("aquifer", "San Asensio", "main", "boreholes"),
                                         ("aquifer", "San Adrián", "main", "boreholes")],
    "Captaciones a ETAP de Errotaberri": generic("ETAP de Errotaberri"),
    "Embalse de Barrendiola y captaciones a embalse": [("reservoir", "Barrendiola", "main", None)],
    "Embalse de Ibaieder": [("reservoir", "Ibaieder", "main", None)],
    "Captaciones superficiales a depósito de Gaztekoa": [("river", None, "main", "surface intakes feeding the Gaztekoa tank")],
    "Embalse de Lareo, captaciones a embalse y captación de Aia-Iturrieta": [
        ("reservoir", "Lareo", "main", None), ("river", "Aia-Iturrieta", "main", None)],
    "Embalse de Arriaran y captaciones a embalse": [("reservoir", "Arriaran", "main", None)],
    "Sondeo Makinetxe": [("aquifer", "Makinetxe", "main", "borehole")],
    "Embalse de Ibiur y captaciones a embalse": [("reservoir", "Ibiur", "main", None)],
    "Captaciones a depósito de Ordizia": generic("the Ordizia tank"),
    "Manantiales de Iñusti y Osinberde": [("spring", "Iñusti", "main", None), ("spring", "Osinberde", "main", None)],
    "Captación superficial Mugitza": [("river", "Mugitza", "main", "surface intake")],
    "Manantiales de Salubieta e Igaran": [("spring", "Salubieta", "main", None), ("spring", "Igaran", "main", None)],
    "Manantial de Berrobi": [("spring", "Berrobi", "main", None)],
    "Captaciones al depósito de Oiamar": generic("the Oiamar tank"),
    "Embalse de Añarbe": [("reservoir", "Añarbe", "main", None)],
    "Captaciones a ETAP de Aia": [("aquifer", "Nacedero Lizartza", "main", "gallery")],
    "Captación superficial Epele 1": [("river", "Epele", "main", "surface intake Epele 1")],
    "Captaciones superficiales Epele 2 y Penadegi": [("river", "Epele", "main", "surface intake Epele 2"),
                                                     ("river", "Penadegi", "main", "surface intake")],
    "Captación superficial Erroizpe Presa": [("river", "Erroizpe", "main", "surface intake at the Erroizpe dam")],
    "Regata Iruritabarrengo": [("river", "regata Iruritabarrengo", "main", None)],
    "Salbide": [("river", "Salbide", "main", "intake; the plan does not give its type")],
    "Manantiales": [("spring", None, "main", None)],
    "Rhune-Chiqui O Yesola": [("river", "Rhune-Chiqui", "main", "also called Yesola; the plan does not give its type")],
    "Regata Matxain - Cuenca Bidasoa": [("river", "regata Matxain", "main", None)],
    "MSBT M. Paleozoicos": [("aquifer", "Macizos Paleozoicos", "main", None)],
    "Sistapor": [("river", "Sistapor", "main", "intake; the plan does not give its type")],
    "Dos Pozos filtrantes": [("aquifer", None, "main", "two filter wells")],
    "ETAP Malerreka": [("network", "ETAP Malerreka", "main", "Malerreka treatment plant, shared with unit Malerreka")],
    "MSBT Basaburua": [("aquifer", "Basaburua-Ulzama", "main", None)],
    "Río Txarutako": [("river", "río Txarutako", "main", None)],
    "Manantial Trosketa": [("spring", "Trosketa", "main", None)],
    "R. Urraba": [("river", "río Urraba", "main", None)],
    "RBidasoa": [("river", "río Bidasoa", "main", None)],
    "Embalses de Endara y Domiko": [("reservoir", "Endara", "main", "also called San Antón"),
                                    ("reservoir", "Domiko", "main", None)],
    "Manantiales y Sondeos Jaizkibel": [("spring", None, "main", "Jaizkibel springs"),
                                        ("aquifer", "Jaizkibel", "main", "Jaizkibel boreholes")],
    "Captaciones a depósitos de sistema Urbanización Jaitzkibel": generic("the tanks of the Urbanización Jaizkibel system"),
}
WATER_BODIES = {"Macizos Paleozoicos": "ES017MSBT017-001", "Basaburua-Ulzama": "ES017MSBT013-012",
                "Jaizkibel": "ES017MSBTES111S000014"}

# Extra sources from the allocation-table footnotes and the narrative: unit -> [(type, name, role, notes, quote)].
# The quote is searched in the PDF to cite the page.
EXTRA = {
    "Mallabia": [("network", "Mañaria-Ermua/Durango-Iurreta (ETAP de Garaizar)", "backup", None,
                  "En caso de necesidad pueden abastecerse de las captaciones que van a la ETAP de Garaizar")],
    "Berriz": [("network", "Mañaria-Ermua/Durango-Iurreta (ETAP de Garaizar)", "backup", None,
                "En caso de necesidad pueden abastecerse de las captaciones que van a la ETAP de Garaizar")],
    "Garai": [("network", "Mañaria-Ermua/Durango-Iurreta (ETAP de Garaizar)", "backup", None,
               "En caso de necesidad pueden abastecerse de las captaciones que van a la ETAP de Garaizar")],
    "Valle Arratia": [("transfer", "Zadorra", "backup", "intakes of ETAP de Venta Alta (Zadorra system)",
                       "En caso de necesidad pueden abastecerse de las captaciones que van a la ETAP de Venta Alta")],
    "Orduña": [("aquifer", "Santa Clara", "backup", "pumping well",
                "En caso de necesidad pueden abastecerse del bombeo de Santa Clara")],
    "Bergara": [("river", None, "backup", "former intakes (Pol-Pol system) kept for emergencies",
                 "Se mantienen las antiguas tomas para posibles situaciones de emergencia")],
    "Antzuola": [("spring", None, "backup", "former intakes (Antzuola springs Akiñabei, Bareño, Laskurain) kept for "
                  "emergencies", "Se mantienen las antiguas tomas para situaciones de emergencia")],
    "Alto Oria": [("reservoir", "Barrendiola", "backup", None,
                   "En caso de necesidad pueden abastecerse del embalse de Barrendiola")],
    "Ordizia resto": [("reservoir", "Arriaran", "backup", None,
                       "En caso de necesidad pueden abastecerse del embalse de Arriaran")],
    "Usurbil": [("reservoir", "Añarbe", "backup", "can take up to 100 % from Añarbe when needed",
                 "el 100 % desde el embalse de Añarbe")],
    "Urb. Jaizkibel": [("reservoir", "Endara", "backup", None,
                        "En caso de necesidad puede abastecerse de los embalses de Endara y Domiko"),
                       ("reservoir", "Domiko", "backup", None,
                        "En caso de necesidad puede abastecerse de los embalses de Endara y Domiko")],
}
# Units the allocation tables leave out: sources from the narrative only.
NARRATIVE = {
    "Abadiño": [("spring", "Garai", "main", "San Salvador system; the allocation table counts Abadiño within "
                 "Duranguesado (ETAP San Salvador 14 %)", "Sistemas Abadiño y San Salvador para el municipio de Abadiño"),
                ("network", "Mañaria-Ermua/Durango-Iurreta (ETAP de Garaizar)", "main", None, "Incluye Abadiño")],
    "Amoroto": [("spring", "Kortezierra", "main", None, "Amoroto (manantiales Kortezierra y Baboliña)"),
                ("spring", "Baboliña", "main", None, "Amoroto (manantiales Kortezierra y Baboliña)")],
    "Eibar": [("reservoir", "Aixola", "main", None, "Sistema Aixola para Eibar"),
              ("reservoir", "Urkulu", "main", "Urkulu system, connected with Aixola",
               "Sistema Urkulu para el Alto Deba y Eibar")],
    "Kilimon": [("spring", "Irabaneta", "main", None, "Kilimon (manantial Irabaneta)"),
                ("aquifer", "K 1-3", "main", "wells", "los pozos K 1-3 del sistema Kilimon")],
    "Deba y Zestoa_parcial": [("river", "arroyo Lastur", "main", "Lastur system",
                               "Sistema Lastur para el resto de Deba y una pequeña parte de Zestoa")],
    "AMVISA": [("reservoir", "Ullibarri-Ganboa", "main", "Ebro basin", "abastecedores de Vitoria"),
               ("reservoir", "Urrunaga", "main", "Ebro basin", "abastecedores de Vitoria"),
               ("reservoir", "Albina", "main", "Ebro basin",
                "el sistema AMVISA cuenta además con el embalse de Albina para abastecer a Vitoria"),
               ("river", "río Zadorra", "main", "pumping at Durana, limited to 0.1296 hm3/month",
                "El bombeo existente en el río Zadorra en Durana para el sistema AMVISA")],
}


def download(out_dir):
    path = os.path.join(out_dir, PDF_NAME)
    if not os.path.exists(path):
        req = urllib.request.Request(URL, headers={"User-Agent": "embalses-open-data/0.1"})
        with urllib.request.urlopen(req, timeout=300) as r, open(path, "wb") as f:
            f.write(r.read())
    return path


def tidy(s):
    return re.sub(r"\s+", " ", s or "").strip(" ,.;")


def squash(s):
    return re.sub(r"\s+", "", s or "")


def fold(s):
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", s).split())


def name_keys(name):
    keys = set()
    for form in [name] + name.split("/"):
        form = form.strip()
        m = re.match(r"(.+),\s*(\w+)$", form)
        keys |= {fold(m.group(1)), fold(m.group(2) + " " + m.group(1))} if m else {fold(form)}
    return keys


def load_reference():
    index = {}
    with open(REFERENCE, newline="") as f:
        for r in csv.DictReader(f):
            if r["province_code"] in PROVINCES:
                for k in name_keys(r["official_name"]):
                    index.setdefault(k, set()).add(r["municipality_code"])
    return index


def pct(s):
    return float(s.replace("%", "").replace(",", ".").strip())


def read_allocations(pdf):
    """Allocation-table rows: unit name -> (pdf page, [(origin label, %)])."""
    out = {}
    for i, page in enumerate(pdf.pages):
        if "Primer origen" not in (page.extract_text() or ""):
            continue
        for table in page.extract_tables():
            for raw in table:
                cells = [tidy(c) for c in raw if tidy(c)]
                if len(cells) < 6 or cells[0] != "UDU":
                    continue
                cells = [re.sub(r"(\w)- (\w)", r"\1-\2", c) for c in cells]   # names wrapped at a hyphen
                name = re.sub(r"(?<=[a-zñ)])\d+$", "", cells[1])       # footnote marks: 'Bilbao6', 'Alto Oria19'
                name = ALLOC_NAMES.get(name, name)
                origins, rest = [], cells[5:]
                k = 0
                while k + 1 < len(rest):
                    label = rest[k]
                    if re.fullmatch(r"[\d,.%]+", label):              # stray numbers ('0%', a lone volume)
                        k += 1
                        continue
                    origins.append((label, pct(rest[k + 1])))
                    k += 3
                out[name] = (i + 1, origins)
    return out


def main():
    out_dir = sys.argv[1] if len(sys.argv) > 1 else "data/raw/plans/cantabrico_oriental"
    os.makedirs(out_dir, exist_ok=True)
    with pdfplumber.open(download(out_dir)) as pdf:
        pages = [squash(p.extract_text()) for p in pdf.pages]
        allocations = read_allocations(pdf)

    def page_of(quote):
        hits = [i + 1 for i, t in enumerate(pages) if squash(quote) in t]
        if not hits:
            raise ValueError(f"quote not found in the annex: {quote!r}")
        return hits[0]

    def check_printed(text):
        """Names wrap across table cells, so check each word is printed in the annex."""
        missing = [w for w in text.split() if not any(squash(w) in t for t in pages)]
        if missing:
            raise ValueError(f"not printed in the annex: {text!r} ({missing})")

    index = load_reference()
    units, links, unmatched = [], [], []
    for prefix, system, rows in UNITS:
        for n, (name, munis) in enumerate(rows, 1):
            code = f"{prefix}{n:02d}"
            check_printed(name)
            units.append((code, name, system))
            for item in [m.strip() for m in re.split(r",\s*(?![^()]*\))", munis)]:
                m = re.match(r"(.+?)\s*\(\s*([\d,]+)\s*%\)$", item)
                plan_name, share = (m.group(1), pct(m.group(2))) if m else (item, None)
                check_printed(plan_name)
                codes = set()
                for k in name_keys(ALIASES.get(plan_name, plan_name)):
                    codes |= index.get(k, set())
                if len(codes) != 1:
                    unmatched.append([plan_name, "/".join(PROVINCES), f"{len(codes)} matches (unit {name})"])
                    continue
                share = COMPLEMENT.get((plan_name, name), share)
                links.append([codes.pop(), code, share, plan_name, name])

    name_to_code = {name: code for code, name, _ in units}
    unknown = set(allocations) - set(name_to_code)
    if unknown:
        raise ValueError(f"allocation rows with no unit: {unknown}")
    sources = []
    for code, name, system in units:
        rows = []
        if name in allocations:
            page, origins = allocations[name]
            for label, share in origins:
                if label not in ORIGINS:
                    raise ValueError(f"no mapping for origin {label!r} ({name}, page {page})")
                mapped = ORIGINS[label]
                for j, (kind, src, role, notes) in enumerate(mapped):
                    extra = f"allocation table PDF p. {page}: '{label}' {share:g} %"
                    carries = len(mapped) == 1 or (j == 0 and label in SHARE_ON_FIRST)
                    rows.append((kind, src, role, share if carries else "",
                                 "; ".join(x for x in (notes, extra) if x)))
        elif name in NARRATIVE:
            for kind, src, role, notes, quote in NARRATIVE[name]:
                rows.append((kind, src, role, "", "; ".join(x for x in (notes, f"narrative PDF p. {page_of(quote)}") if x)))
        else:
            raise ValueError(f"no sources for unit {name}")
        for kind, src, role, notes, quote in EXTRA.get(name, []):
            rows.append((kind, src, role, "", "; ".join(x for x in (notes, f"PDF p. {page_of(quote)}") if x)))
        seen = set()
        rank = 0
        for kind, src, role, share, notes in rows:
            if src and (kind, src) in seen:
                continue
            seen.add((kind, src))
            rank += 1
            sources.append([code, "", rank, kind, src or "", role, WATER_BODIES.get(src, ""), share, notes])

    with open(os.path.join(out_dir, "supply_units.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["unit_code", "unit_name"])
        for code, name, _ in units:
            w.writerow([code, name])
    with open(os.path.join(out_dir, "municipality_supply.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["municipality_code", "unit_code", "share_pct", "intake_description", "additional_intakes"])
        for muni, code, share, _, _ in sorted(links):
            w.writerow([muni, code, "" if share is None else f"{share:g}", "", ""])
    with open(os.path.join(out_dir, "supply_sources.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["unit_code", "municipality_code", "source_rank", "source_type", "source_name", "role",
                    "water_body_code", "share_pct", "notes"])
        for s in sources:
            s[7] = "" if s[7] == "" else f"{s[7]:g}"
            w.writerow(s)
    with open(os.path.join(out_dir, "unmatched.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["plan_name", "province_hint", "reason"])
        w.writerows(unmatched)

    meta = {
        "plan": "cantabrico_oriental", "basin_id": "ES017", "source": "ph-cantabrico-oriental-2022-2027",
        "plan_cycle": "2022-2027",
        "source_document": "Plan Hidrológico de la Demarcación Hidrográfica del Cantábrico Oriental, revisión de "
                           "tercer ciclo 2022-2027 (Real Decreto 35/2023), Anejo VI Asignación y reserva de recursos: "
                           "per exploitation system, 'Valores anuales de demanda para las UDUs incluidas en el modelo' "
                           "and 'Asignación y reserva de recursos' tables, and the system descriptions",
        "source_url": URL,
        "notes": ("One joint annex for the Basque intra-community basins and the state part of the district; the URA "
                  "and CHC copies are byte-identical. The plan names its urban units but gives them no codes: "
                  "unit_code is a system prefix (IBB Ibaizabal-Butroe-Barbadun, OKA, LEA Lea-Artibai, DEB Deba, "
                  "URO Urola, ORI Oria, URU Urumea-Oiartzun, BID Bidasoa) plus the row order of the demand table. "
                  "share_pct on municipality_supply is the plan's own '(nn%)'; for Zestoa in Ibaieder (99) and "
                  "Urnieta in Añarbe (91.5) it is the complement of the share printed for their other unit. "
                  "Sources come from the allocation tables (2027 allocation, origins with %): an origin that is one "
                  "source carries its % as share_pct, an origin that groups several (\"Embalses de Ordunte y Zollo\") "
                  "gives the % in notes. Origins worded only as 'Captaciones a ETAP de X' were typed from the "
                  "system descriptions (springs, boreholes) where the annex names them; otherwise they are typed "
                  "river with the note 'the plan does not give their type'. The Zadorra transfer is listed as a "
                  "transfer plus the Ullibarri-Ganboa and Urrunaga reservoirs it draws on (Ebro basin). Units "
                  "missing from the allocation tables (Abadiño, Amoroto, Eibar, Kilimon, Deba y Zestoa_parcial, "
                  "AMVISA) take their sources from the narrative, cited by PDF page in notes. AMVISA (Vitoria-Gasteiz "
                  "and neighbours) lies in the Ebro district but is part of this plan's Zadorra model and demand "
                  "table, so it is included. The Ereño unit is in the Oka allocation table and narrative only. "
                  "Systems the annex names but leaves out of the model (small village systems) have no rows."),
    }
    with open(os.path.join(out_dir, "meta.json"), "w") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
        f.write("\n")
    counts = {}
    for s in sources:
        counts[s[3]] = counts.get(s[3], 0) + 1
    print(f"{len(units)} units, {len({l[0] for l in links})} municipalities ({len(links)} links), {len(sources)} "
          f"sources {counts}, {len(unmatched)} unmatched, {len(allocations)} allocation rows -> {out_dir}")


if __name__ == "__main__":
    main()
