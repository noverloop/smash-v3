"""Per-part component catalog.

Each submodule holds `add_<partnumber>(design, ref, **overrides)` factories.
Every factory is a faithful transcription of a single manufacturer's
ground-truth artifacts (datasheet PDF, SamacSys ZIP, KiCad symbol +
footprint + 3D, distributor listing). The artifacts live alongside the
factory in `parts/sources/<PARTNUMBER>/`.

Discipline:

  * Never invent values. If a field has no source in the artifacts,
    leave it `None` (or `[]`) and record the gap in `note`.
  * Transcribe strings verbatim from the datasheet — no paraphrasing.
  * One factory per concrete orderable part number. If a single
    datasheet covers a family (e.g. LDL112PVxxR), produce one factory
    per orderable PN, optionally sharing a private `_base()` helper.
  * Factories return the constructed Chip (or Battery) so callers can
    immediately wire it via `chip.pin('G')` etc.
"""

from smash.parts.mosfets import (
    add_irlml6402trpbf,
    add_irlml6244trpbf,
    add_bss138lt1g,
    add_dmn6075sq_7,
    add_dmp6110svt_7,
)
from smash.parts.ldos import (
    add_ldl112pv33r,
    add_tps7a0233pdbvr,
    add_ldl112pv18r,
    add_stlq020j30r,
    add_stlq020j33r,
    add_stlq020c33r,
    add_lp5907mfx_1_2_nopb,
    add_lp5907mfx_2_8_nopb,
)
from smash.parts.leds import (
    add_ltst_c190gkt,
)
from smash.parts.regulators import (
    add_mcp1640ct_i_chy,
    add_lmr10510xmfe_nopb,
    add_tps61085pw,
    add_tps61175pwpr,
)
from smash.parts.diodes import (
    add_mbrs340t3g,
    add_mbrs540t3g,
    add_pmeg040v050epe_qz,
)
from smash.parts.comparators import (
    add_lmv331idbvr,
    add_tlv3691idpfr,
)
from smash.parts.sensors import (
    add_tmp117maidrvr,
    add_iis2mdctr,
    add_ism330dhcxtr,
    add_h3lis331dltr,
)
from smash.parts.transceivers import (
    add_tcan1042gvdq1,
)
from smash.parts.oscillators import (
    add_dsc1001ci5_008_0000,
    add_dsc1001ci5_032_0000,
    add_dsc1001ci5_040_0000,
    add_sit1630ae_s6_dcc_32_768e,
)
from smash.parts.efuses import (
    add_tps25940aqrvctq1,
    add_tps259621ddar,
)
from smash.parts.memory import (
    add_m24c01_rmn6tp,
)
from smash.parts.opamps import (
    add_ad8603aujz_r2_single_supply,
    add_ad8603aujz_r2_dual_supply,
)
from smash.parts.rf import (
    add_bgs12wn6e6327xtsa1,
    add_adf4351bcpz,
)
from smash.parts.passives import (
    add_we_744043100,
    # Family-parameterized passive factories (Group D)
    add_resistor_0402_vishay,
    add_capacitor_x7r_0402_kemet,
    add_capacitor_x7r_0603_kemet_mil,
    add_capacitor_x7r_0805_kemet_mil,
    add_capacitor_c0g_0603_avx_sqcs,
    add_capacitor_tantalum_3528_kemet_t491,
    add_capacitor_polymer_7343_kemet_t528,
    add_capacitor_svpf_25v_330uf_panasonic,
    add_inductor_we_ki_0402_wurth,
    add_inductor_tms201210alm_tdk,
)
from smash.parts.nfc import add_st25dv16kc_ie8t3
from smash.parts.motor_drivers import add_drv8833pwr, add_drv8711dcpr
from smash.parts.flash import (
    add_s25hl512tfamhi010,
    add_sst26wf080b,
    add_sst26vf080a,
    add_mt29f4g01abafdwb_it_f,
    add_mt29f4g01abafd12_aat_f,
    add_mt29f8g08abacah4_it_c_tr,
    add_mt29f8g08abacawp_it_c,
    add_mt41k256m16tw_107_ptr,
    add_as4c512m16d3lc_12bin,
    add_ktdm4g4b626bgieat,
    add_mx60lf8g28ad_xki_t,
)
from smash.parts.mcus import (
    add_stm32g0b1kct6n,
    add_stm32g0b1kcu6n,
    add_stm32g0b1rei6n,
    add_stm32wle5jci6,
    add_stm32wba52cgu7tr,
    add_stm32wba55hgf6tr,
    add_stm32h562aii6,
    add_stm32mp255fak3,
    add_stm32mp255dal3,
)
from smash.parts.wireless import add_lbee5kl1yn_814
from smash.parts.pmics import add_stpmic25apqr
from smash.parts.radar import (
    add_iwr1843arqgalpr,
    add_awr1843aop,
    add_awr2944abgaltq1,
    add_awr2944abgaltrq1,
    add_awr2944albgaltrq1,
    add_awr2243abgablq1,
    add_awr2243abgablrq1,
    add_awr2e44pbgamxrq1,
)
from smash.parts.diodes import add_bat64_06_tp
from smash.parts.optical import add_sfh203fa, add_vbpw34fas, add_vsmb1940x01
from smash.parts.hall_sensors import add_drv5023ajqlpg, add_drv5032fcqdbzr, add_rr123_1h02_612
from smash.parts.cameras import add_ar0234cssm00suka0_cp
from smash.parts.usb import (
    add_uj31_ch_3_msmt_tr_67,
    add_uj20_c_h_g_msmt_1a_p16_tr_67,
)
from smash.parts.mechanical import (
    add_cellattach_3x2_tlm1520,
    add_cell_contacts_3,
    add_piezo_disc_smd10t04r111,
    add_pogo_pad,
    add_mechanical_spacer_34mm,
    add_nfc_antenna_flex_27x50,
    add_mt03_092_qpd,
)
from smash.parts.batteries import add_tlm_1520hpms
from smash.parts.logic import (
    add_sn74lvc1g08dbvr, add_sn74lvc1g08dckrg4, add_cd74hc4514pw,
)

__all__ = [
    # mosfets
    "add_irlml6402trpbf",
    "add_irlml6244trpbf",
    "add_bss138lt1g",
    "add_dmn6075sq_7",
    "add_dmp6110svt_7",
    # ldos
    "add_ldl112pv33r",
    "add_tps7a0233pdbvr",
    "add_ldl112pv18r",
    "add_stlq020j30r",
    "add_stlq020j33r",
    "add_stlq020c33r",
    "add_lp5907mfx_1_2_nopb",
    "add_lp5907mfx_2_8_nopb",
    # leds
    "add_ltst_c190gkt",
    # switching regulators
    "add_mcp1640ct_i_chy",
    "add_lmr10510xmfe_nopb",
    "add_tps61085pw",
    "add_tps61175pwpr",
    # diodes
    "add_mbrs340t3g",
    "add_mbrs540t3g",
    "add_pmeg040v050epe_qz",
    "add_bat64_06_tp",
    # comparators
    "add_lmv331idbvr",
    "add_tlv3691idpfr",
    # sensors
    "add_tmp117maidrvr",
    "add_iis2mdctr",
    "add_ism330dhcxtr",
    "add_h3lis331dltr",
    # bus transceivers
    "add_tcan1042gvdq1",
    # oscillators
    "add_dsc1001ci5_008_0000",
    "add_dsc1001ci5_032_0000",
    "add_dsc1001ci5_040_0000",
    "add_sit1630ae_s6_dcc_32_768e",
    # eFuses
    "add_tps25940aqrvctq1",
    "add_tps259621ddar",
    # memory
    "add_m24c01_rmn6tp",
    # op-amps
    "add_ad8603aujz_r2_single_supply",
    "add_ad8603aujz_r2_dual_supply",
    # RF parts
    "add_bgs12wn6e6327xtsa1",
    "add_adf4351bcpz",
    # passives
    "add_we_744043100",
    # Group D — family-parameterized passives
    "add_resistor_0402_vishay",
    "add_capacitor_x7r_0402_kemet",
    "add_capacitor_x7r_0603_kemet_mil",
    "add_capacitor_x7r_0805_kemet_mil",
    "add_capacitor_c0g_0603_avx_sqcs",
    "add_capacitor_tantalum_3528_kemet_t491",
    "add_capacitor_polymer_7343_kemet_t528",
    "add_capacitor_svpf_25v_330uf_panasonic",
    "add_inductor_we_ki_0402_wurth",
    "add_inductor_tms201210alm_tdk",
    # NFC
    "add_st25dv16kc_ie8t3",
    # motor drivers
    "add_drv8833pwr", "add_drv8711dcpr",
    # flash + DRAM
    "add_s25hl512tfamhi010",
    "add_sst26wf080b",
    "add_sst26vf080a",
    "add_mt29f4g01abafdwb_it_f", "add_mt29f4g01abafd12_aat_f",
    "add_mt29f8g08abacah4_it_c_tr", "add_mt29f8g08abacawp_it_c",
    "add_mt41k256m16tw_107_ptr", "add_as4c512m16d3lc_12bin",
    "add_ktdm4g4b626bgieat",
    "add_mx60lf8g28ad_xki_t",
    # MCUs
    "add_stm32g0b1kct6n", "add_stm32g0b1kcu6n", "add_stm32g0b1rei6n",
    "add_stm32wle5jci6", "add_stm32wba52cgu7tr", "add_stm32wba55hgf6tr",
    "add_stm32h562aii6", "add_stm32mp255fak3", "add_stm32mp255dal3",
    # wireless / PMIC / radar
    "add_lbee5kl1yn_814",
    "add_stpmic25apqr",
    "add_iwr1843arqgalpr",
    "add_awr1843aop",
    "add_awr2944abgaltq1", "add_awr2944abgaltrq1", "add_awr2944albgaltrq1",
    "add_awr2243abgablq1", "add_awr2243abgablrq1",
    "add_awr2e44pbgamxrq1",
    # photodiode + Hall sensor + camera
    "add_sfh203fa", "add_vbpw34fas", "add_vsmb1940x01", "add_drv5023ajqlpg",
    "add_drv5032fcqdbzr", "add_rr123_1h02_612",
    "add_ar0234cssm00suka0_cp",
    # USB-C connector
    "add_uj31_ch_3_msmt_tr_67",
    "add_uj20_c_h_g_msmt_1a_p16_tr_67",
    # project-built custom footprints (mechanical / connector / antenna)
    "add_cellattach_3x2_tlm1520",
    "add_cell_contacts_3",
    "add_piezo_disc_smd10t04r111",
    "add_pogo_pad",
    "add_mechanical_spacer_34mm",
    "add_nfc_antenna_flex_27x50",
    "add_mt03_092_qpd",
    # battery
    "add_tlm_1520hpms",
    # logic gates
    "add_sn74lvc1g08dbvr",
    "add_sn74lvc1g08dckrg4",
    "add_cd74hc4514pw",
]
