#!/usr/bin/env bash
# Scarica i datasheet della fin_ble_board. Uso: bash _download.sh
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
get() { # file ruolo url...
  f="$1"; r="$2"; shift 2
  for u in "$@"; do
    if curl -fsSL -A "$UA" --max-time 60 -o "$f.tmp" "$u" && head -c 5 "$f.tmp" | grep -q "%PDF"; then
      mv "$f.tmp" "$f"; echo "OK   $f  ($(stat -c %s "$f") byte)  <- $u"; echo "$f|$r|$u|ok" >> _manifest.txt; return
    fi
  done
  rm -f "$f.tmp"; echo "FAIL $f"; echo "$f|$r|$*|failed" >> _manifest.txt
}
: > _manifest.txt
get STM32G0B1RE_ds.pdf "MCU STM32G0B1REI6N (UFBGA64)" \
  https://www.st.com/resource/en/datasheet/stm32g0b1re.pdf \
  https://www.mouser.com/datasheet/2/389/stm32g0b1re-2402549.pdf
get STM32G0_RM0444.pdf "Reference manual STM32G0x1" \
  https://www.st.com/resource/en/reference_manual/rm0444-stm32g0x1-advanced-armbased-32bit-mcus-stmicroelectronics.pdf
get AN5096_STM32G0_hardware.pdf "AN5096 getting started hardware STM32G0" \
  https://www.st.com/resource/en/application_note/an5096-getting-started-with-stm32g0-series-hardware-development-stmicroelectronics.pdf
get AN4822_BGA_PCB_design.pdf "AN4822 PCB design with 0.5mm pitch UFBGA" \
  https://www.st.com/resource/en/application_note/an4822-pcb-design-guidelines-for-reduced-pitch-bga-packages-stmicroelectronics.pdf
get DRV8428_ds.pdf "Stepper driver DRV8428EPWPR x4" https://www.ti.com/lit/ds/symlink/drv8428.pdf
get TLV3691_ds.pdf "Comparatore nanopower TLV3691IDPFR" https://www.ti.com/lit/ds/symlink/tlv3691.pdf
get KEMET_MIL-PRF-32535_C-Series.pdf "Condensatori MIL-PRF-32535" \
  https://content.kemet.com/datasheets/KEM_C1106_MIL-PRF-32535.pdf \
  https://www.kemet.com/content/dam/kemet/lightning/documents/ec-content/KEM_C1106_MIL-PRF-32535.pdf
get KEMET_X7R_commercial.pdf "Condensatori 0402 X7R commerciali" \
  https://content.kemet.com/datasheets/KEM_C1002_X7R_SMD.pdf
get Vishay_CRCW_e3.pdf "Resistenze CRCW0402 e3" https://www.vishay.com/docs/20035/dcrcwe3.pdf
get Steminc_SMD10T04R111.pdf "Piezo SMD10T04R111" \
  https://www.steminc.com/PZT/en/content/pdf/SMD10T04R111.pdf \
  https://www.steminc.com/piezo/PDF/SMD10T04R111.pdf
