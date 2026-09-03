import { NgModule } from '@angular/core';
import { BrowserModule } from '@angular/platform-browser';
import { HttpClientModule, HTTP_INTERCEPTORS } from '@angular/common/http';
import { FormsModule } from '@angular/forms';
import { MarkdownModule } from 'ngx-markdown';

import { AppComponent } from './app.component';
import { LoadingInterceptor } from '../shared/interceptors/loader';
import { Spinner } from '../shared/spinner/spinner';
import { RouterModule } from '@angular/router';
import { GlobalSpinner } from '../shared/global-spinner/global-spinner';

@NgModule({
  declarations: [
    AppComponent,
    Spinner,
    GlobalSpinner
  ],
  imports: [
    BrowserModule,
    HttpClientModule,
    FormsModule,
    RouterModule.forRoot([]),

    MarkdownModule.forRoot()
  ],
  providers: [
    { provide: HTTP_INTERCEPTORS, useClass: LoadingInterceptor, multi: true }
  ],
  bootstrap: [AppComponent]
})
export class AppModule { }
