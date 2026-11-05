"""Static choices for synthetic invoices: products, templates and print formats."""

PRODUCTS: tuple[tuple[str, int, int], ...] = (
    # Alat tulis kantor (ATK)
    ("Kertas HVS A4 80gsm (rim)", 45000, 65000),
    ("Kertas HVS F4 70gsm (rim)", 42000, 60000),
    ("Pulpen gel hitam (lusin)", 30000, 55000),
    ("Map plastik kancing (pak)", 25000, 40000),
    ("Tinta printer hitam 70ml", 75000, 120000),
    ("Toner laser jet 85A", 350000, 650000),
    ("Stapler besar HD-50", 85000, 140000),
    ("Ordner folio 7cm", 28000, 45000),
    ("Spidol whiteboard (lusin)", 60000, 95000),
    ("Amplop coklat F4 (pak)", 35000, 55000),
    # Jasa logistik
    ("Jasa pengiriman Jakarta-Bandung", 150000, 450000),
    ("Jasa pengiriman Surabaya-Makassar", 900000, 2500000),
    ("Sewa truk engkel per hari", 1200000, 2000000),
    ("Biaya bongkar muat (per ton)", 75000, 150000),
    ("Asuransi pengiriman barang", 50000, 300000),
    ("Jasa gudang per palet per bulan", 250000, 450000),
    ("Packing kayu ekspedisi", 80000, 250000),
    # Sembako
    ("Beras premium 25kg", 340000, 420000),
    ("Minyak goreng 2L (karton)", 180000, 230000),
    ("Gula pasir 50kg", 780000, 900000),
    ("Tepung terigu 25kg", 230000, 290000),
    ("Telur ayam (peti 15kg)", 380000, 450000),
    ("Kopi bubuk 1kg", 90000, 160000),
    ("Teh celup (karton)", 120000, 180000),
    ("Air mineral galon 19L", 18000, 25000),
    # Jasa IT
    ("Lisensi antivirus 1 tahun", 250000, 450000),
    ("Jasa instalasi jaringan LAN", 1500000, 4500000),
    ("Sewa server cloud per bulan", 750000, 3500000),
    ("Maintenance komputer per unit", 150000, 300000),
    ("Pembuatan website company profile", 5000000, 15000000),
    ("Langganan internet dedicated 50Mbps", 2500000, 6000000),
    ("Kabel UTP Cat6 (box 305m)", 1300000, 2100000),
    ("Router wireless AX3000", 1100000, 2400000),
)

TEMPLATES = ("modern", "klasik", "minimal")

# long_id: 05 November 2026, dmy_slash: 05/11/2026, iso: 2026-11-05, short_en: 5 Nov 2026
DATE_FORMATS = ("long_id", "dmy_slash", "iso", "short_en")

# rp_dot: Rp 1.234.567, dot_comma: 1.234.567,00, idr_comma: IDR 1,234,567
NUMBER_STYLES = ("rp_dot", "dot_comma", "idr_comma")

INVOICE_NUMBER_FORMATS = ("INV/{y}/{m:02d}/{n:05d}", "FK-{n:06d}", "{y}.{m:02d}.{n:04d}")
