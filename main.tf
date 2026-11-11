# embalses on LakehouseBox, as OpenTofu / Terraform.
#
# The same deployment as lakehouse.yaml (which `lhbox apply` reads), for teams that keep infrastructure in Terraform:
# the public catalog, what its scheduled SQL may reach, the 14 sinks that keep it filled, and its documentation.
# Tables are not here: they come from sql/migrations/ (`lhbox migrate`), so no apply can drop a table or its rows.
#
#   export LHBOX_API_KEY=...        # `lhbox login` makes one
#   tofu init && tofu plan
#
# To adopt the catalog that already exists, import first (see README, "Terraform").

terraform {
  required_providers {
    lakehousebox = { source = "lakehousebox/lakehousebox", version = "~> 0.1" }
  }
}

provider "lakehousebox" {}

locals {
  # Scheduled SQL over public URLs: LakehouseBox fetches the official sources itself and appends to obs.*
  ingest = {
    saih_ebro               = { table = "obs.reservoir_readings", sql = "sql/ingest/reservoir_readings_ebro.sql", every = "15m", offset = "2m" }
    saih_guadalquivir       = { table = "obs.reservoir_readings", sql = "sql/ingest/reservoir_readings_guadalquivir.sql", every = "15m", offset = "4m" }
    saih_segura             = { table = "obs.reservoir_readings", sql = "sql/ingest/reservoir_readings_segura.sql", every = "15m", offset = "6m" }
    saih_minosil            = { table = "obs.reservoir_readings", sql = "sql/ingest/reservoir_readings_minosil.sql", every = "15m", offset = "8m" }
    saih_cantabrico         = { table = "obs.reservoir_readings", sql = "sql/ingest/reservoir_readings_cantabrico.sql", every = "15m", offset = "10m" }
    saih_guadiana           = { table = "obs.reservoir_readings", sql = "sql/ingest/reservoir_readings_guadiana.sql", every = "1h", offset = "12m" } # one request per reservoir, so hourly
    miteco_reservoir_weekly = { table = "obs.reservoir_weekly", sql = "sql/ingest/reservoir_weekly.sql", every = "1d", offset = "6h" }               # weekly bulletin, published Tuesdays
    aemet_precipitation     = { table = "obs.precipitation", sql = "sql/ingest/aemet_precipitation.sql", every = "30m", offset = "23m" }
    aemet_weather           = { table = "obs.weather", sql = "sql/ingest/aemet_weather.sql", every = "30m", offset = "23m" }
  }

  # Derived tables: scheduled SQL that reads the catalog itself; each run replaces the table.
  derived = {
    now_rain_grid        = { table = "now.rain_grid", sql = "sql/now/rain_grid.sql", offset = "28m", min_rows = 1000 }
    now_upstream_rain    = { table = "now.upstream_rain", sql = "sql/now/upstream_rain.sql", offset = "31m", min_rows = 300 }
    now_reservoir_status = { table = "now.reservoir_status", sql = "sql/now/reservoir_status.sql", offset = "34m", min_rows = 300 }
    now_basin_summary    = { table = "now.basin_summary", sql = "sql/now/basin_summary.sql", offset = "37m", min_rows = 10 }
    now_station_status   = { table = "now.station_status", sql = "sql/now/station_status.sql", offset = "40m", min_rows = 300 }
  }

  # Where scheduled SQL may send a request body: the form POSTs of three SAIH viewers.
  post_prefixes = toset([
    "https://saihweb.chsegura.es/apps/iVisor/",
    "https://visor.saichcantabrico.es/wp-admin/",
    "https://siraguadiana.com/backend/",
  ])

  table_docs = jsondecode(file("${path.module}/docs/table_docs.json"))
}

resource "lakehousebox_catalog" "embalses" {
  name                   = "embalses"
  default_format_version = 3 # geometry columns (Iceberg v3 GEOMETRY)
  public                 = true
}

resource "lakehousebox_sql_post_prefix" "saih" {
  for_each   = local.post_prefixes
  catalog    = lakehousebox_catalog.embalses.name
  url_prefix = each.value
}

# The AEMET key is the organisation's web integration, not a copy: it never appears here or in state.
resource "lakehousebox_sql_connection" "aemet" {
  catalog     = lakehousebox_catalog.embalses.name
  name        = "aemet"
  integration = "aemet"
}

resource "lakehousebox_sql_sink" "ingest" {
  for_each = local.ingest
  catalog  = lakehousebox_catalog.embalses.name
  name     = each.key
  table    = each.value.table
  sql      = file("${path.module}/${each.value.sql}")
  every    = each.value.every
  offset   = each.value.offset

  depends_on = [lakehousebox_sql_post_prefix.saih, lakehousebox_sql_connection.aemet]
}

resource "lakehousebox_sql_sink" "derived" {
  for_each = local.derived
  catalog  = lakehousebox_catalog.embalses.name
  name     = each.key
  table    = each.value.table
  sql      = file("${path.module}/${each.value.sql}")
  every    = "1h"
  offset   = each.value.offset
  mode     = "replace"
  min_rows = each.value.min_rows
}

resource "lakehousebox_catalog_agents_md" "embalses" {
  catalog = lakehousebox_catalog.embalses.name
  text    = file("${path.module}/docs/AGENTS.md")
}

resource "lakehousebox_table_description" "docs" {
  for_each    = local.table_docs
  catalog     = lakehousebox_catalog.embalses.name
  table       = each.key
  description = each.value.doc
  columns     = each.value.columns
}
