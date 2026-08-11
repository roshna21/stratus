# The demo page

Served from a storage account that Stratus itself created, from the request
`"a small website that can store uploaded files"`.

Publish it with:

```bash
az storage blob upload-batch \
  --account-name <the storage account Stratus made> \
  --auth-mode key \
  --destination '$web' \
  --source demo-site \
  --overwrite
```

`--auth-mode key` rather than `login`: owning a subscription grants control
over a storage account but not access to the data inside it — those are
separate permission systems in Azure. The key route works because an owner
can retrieve the key; the alternative is granting yourself
**Storage Blob Data Contributor** on the account first.
