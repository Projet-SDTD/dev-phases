# syntax=docker/dockerfile:1

FROM golang:1.19.5-alpine3.17 AS build

WORKDIR /app

COPY go.mod ./
COPY go.sum ./
RUN go mod download

COPY *.go ./

RUN go build -o /kube_deployment

FROM alpine:3.17

WORKDIR /

COPY --from=build /kube_deployment /kube_deployment

EXPOSE 3333

USER nonroot:nonroot

CMD [ "/kube_deployment" ] 
