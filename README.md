# Xiaomi Unlock Community Helper - Multi Offset (Linux Mint)

Versi praktis untuk Linux Mint dengan beberapa offset waktu.

## Default timing

Script mengirim maksimal 4 request terjadwal:

- 1000 ms sebelum 00:00 GMT+8
- 500 ms sebelum 00:00 GMT+8
- 150 ms sebelum 00:00 GMT+8
- tepat 00:00 GMT+8

Begitu mendapat `approved`, script berhenti dan tidak mengirim request berikutnya.

Jika server mengembalikan `limit` sebelum 00:00, script masih lanjut ke offset berikutnya karena itu bisa saja masih kuota hari sebelumnya. Jika `limit` muncul pada/selepas 00:00, script berhenti.

## Menjalankan

```bash
chmod +x START.sh
./START.sh
```

Untuk memakai offset sendiri:

```bash
./START.sh --offsets 1200,700,300,0
```

Hanya cek status akun:

```bash
./START.sh --check-only
```

## Login Xiaomi

Jika session Xiaomi Community belum ditemukan, Firefox akan dibuka ke:

https://new.c.mi.com/global

Login dengan akun Xiaomi yang sama seperti di tablet, kemudian tutup Firefox dan tekan ENTER di terminal.

## Catatan keamanan

- Token session hanya disimpan sementara di RAM.
- Tidak ada loop request tanpa batas.
- Maksimal jumlah request sama dengan jumlah offset yang Anda tentukan.
- Script tidak menjamin kuota Xiaomi tersedia atau permohonan pasti diterima.
