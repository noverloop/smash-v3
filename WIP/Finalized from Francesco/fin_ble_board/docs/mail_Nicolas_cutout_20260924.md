# Mail a Nicolas – fin_ble_board, posizionamento rispetto ai cutout

*Bozza del 24/09/2026 – non ancora inviata*

---

## Versione italiana

**Oggetto:** fin_ble_board – posizionamento dei componenti rispetto ai cutout degli spacer

Ciao Nicolas,

ti confermo come abbiamo interpretato il tuo commento sul vano batterie:

- I **componenti sul lato bottom** devono stare dentro i cutout delle batterie, cioè la sagoma su B.Silkscreen (3 × Ø 15,2 mm).
- I **componenti sul lato top** devono stare dentro la finestra dello spacer verso la wakeup, cioè la sagoma su F.Silkscreen.
- Le piazzole LGA restano fuori da entrambe le sagome, sull'anello pieno dello spacer.

Terremo almeno 0,2 mm dal bordo dei cutout, per coprire la tolleranza di fresatura dello spacer. Oggi il lato top è tutto in regola. Sul bottom, due pogo pad (J_HALL_FIN_VCC e J_HALL_FIN_OUT) sporgono di 0,1–0,2 mm e due condensatori 0805 sono troppo vicini al bordo: li sposteremo.

Due domande:

1. **Altezza**: quanto spazio c'è fra la scheda e la spalla della cella, intorno al contatto positivo? Alcuni condensatori sul bottom sono 0805 alti fino a 1,25 mm.
2. **Pogo pad J_HALL_FIN**: cosa li contatta da sotto, visto che si trovano sopra le celle?

Grazie,
Francesco

---

## English version

**Subject:** fin_ble_board – component placement vs spacer cutouts

Hi Nicolas,

Quick confirmation on your comment about the battery compartment. We read it as:

- **Bottom-side parts** must sit inside the battery cutouts (B.Silkscreen outline, 3 × Ø15.2 mm).
- **Top-side parts** must sit inside the wakeup-spacer window (F.Silkscreen outline).
- The LGA lands stay outside both outlines, on the solid spacer ring.

We will keep at least 0.2 mm from the cutout edges, to cover the spacer milling tolerance. Today the top side is fully compliant. On the bottom, two pogo pads (J_HALL_FIN_VCC and J_HALL_FIN_OUT) stick out by 0.1–0.2 mm and two 0805 caps are too close to the edge. We will move them.

Two questions:

1. **Height**: how much clearance is there between the board and the cell shoulder around the + contact? Some bottom caps are 0805 parts up to 1.25 mm tall.
2. **J_HALL_FIN pogo pads**: what makes contact with them from below, given that they sit over the cells?

Thanks,
Francesco

---

## Esito

*24/09/2026* – Nicolas ha confermato l'interpretazione: componenti bottom dentro B.Silkscreen (cutout celle), componenti top dentro F.Silkscreen (finestra spacer wakeup).

Applicato (script `scripts_NCAB/fin_move4.py`, backup in `backup_pre_cutout_20260924/`): margine minimo 0,20 mm dal bordo dei cutout.

| Componente | Da | A | Margine |
|---|---|---|---|
| J_HALL_FIN_VCC | (2,50; −0,50) | (3,20; 0,18) | −0,22 → +0,20 mm |
| J_HALL_FIN_OUT | (−3,00; −1,00) | (−3,34; −0,60) | −0,09 → +0,20 mm |
| C_G0B1_FIN_BULK | (12,50; 6,50) | (12,48; 6,49) | +0,18 → +0,21 mm |
| C_FIN4_DVDD | (1,44; 4,56) | (1,86; 4,54) | +0,19 → +0,20 mm |

Ancora senza risposta: altezza disponibile sopra la spalla delle celle; cosa contatta i pogo pad J_HALL_FIN.
